import calendar
import re
import unicodedata
from datetime import date
from pathlib import Path
from uuid import uuid4

import pandas as pd
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)



# 1. NORMALIZAR TEXTOS


def normalizar_texto(valor):
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return " ".join(texto.split())



# 2. VALIDAR FECHAS


def validar_fechas(fecha_inicio, fecha_termino):
    """Valida fechas AAAA-MM-DD y un rango máximo de un mes."""
    try:
        inicio = date.fromisoformat(fecha_inicio)
        termino = date.fromisoformat(fecha_termino)
    except (TypeError, ValueError):
        raise ValueError(
            "Ingrese ambas fechas correctamente."
        ) from None
    
    if inicio > termino:
        raise ValueError(
            "La fecha de inicio no puede ser posterior "
            "a la fecha de término."
        )
    
    mes_siguiente = inicio.month % 12 + 1
    anio_siguiente = inicio.year + (inicio.month == 12)

    ultimo_dia = calendar.monthrange(
        anio_siguiente,
        mes_siguiente,
    )[1]

    limite = date(
        anio_siguiente,
        mes_siguiente,
        min(inicio.day, ultimo_dia),
    )

    if termino > limite:
        raise ValueError(
            "WebLun permite consultar un rango máximo de un mes."
        )
    
    return inicio, termino



# 3. IDENTIFICAR Y COMPLETAR LOS CAMPOS DE FECHA


def localizar_fecha(page, etiqueta, posicion):
    """Busca por etiqueta o por los dos campos visibles."""
    campo = page.get_by_label(etiqueta, exact=True)

    if campo.count() == 1:
        return campo
    
    campos = page.locator(
        'input:visible:not([type="hidden"])'
        ':not([type="button"]):not([type="submit"])'
        ':not([type="checkbox"]):not([type="radio"])'
    )

    if campos.count() != 2:
        raise RuntimeError(
            f"No se pudo identificar el campo '{etiqueta}'. "
            "Es necesario revisar su selector."
        )
    
    return campos.nth(posicion)


def completar_fecha(campo, fecha):
    formato = (
        fecha.isoformat()
        if campo.get_attribute("type") == "date"
        else fecha.strftime("%d-%m-%Y")
    )

    campo.fill(formato)
    campo.press("Tab")



# 4. MOSTRAR EL DIAGNÓSTICO DE LOS CAMPOS DEL REPORTE


def diagnosticar_campos_reporte(page):
    """Muestra atributos y etiquetas, sin imprimir valores."""
    campos = page.locator("input").evaluate_all("""
        elementos => elementos.map(elemento => ({
            type: elemento.type,
            id: elemento.id,
            name: elemento.name,
            placeholder: elemento.placeholder,
            visible: Boolean(elemento.getClientRects().length)
        }))
    """)

    etiquetas = page.locator("label").evaluate_all("""
        elementos => elementos.map(elemento => ({
            texto: elemento.textContent.trim(),
            for: elemento.htmlFor
        }))
    """)

    print("Campos del reporte:", campos)
    print("Etiquetas del reporte:", etiquetas)



# 5. LIMPIAR EL EXCEL


def limpiar_excel(ruta_original, ruta_destino):
    """Conserva activos, elimina filas iguales y agrega filtros."""
    tabla = pd.read_excel(
        ruta_original,
        header=None,
        dtype=str,
        keep_default_na=False,
    )

    indice_cabecera = None

    for indice, fila in tabla.head(30).iterrows():
        nombres = [
            normalizar_texto(valor)
            for valor in fila
        ]

        if (
            ("run" in nombres or "rut" in nombres)
            and "estado actual" in nombres
        ):
            indice_cabecera = indice
            break

    if indice_cabecera is None:
        raise ValueError(
            "No se encontró una cabecera con RUN/RUT "
            "y Estado actual en el Excel."
        )
    
    columnas = [
        " ".join(str(valor).split())
        for valor in tabla.loc[indice_cabecera]
    ]

    df = tabla.loc[indice_cabecera + 1:].copy()
    df.columns = columnas
    
    # Descarta columnas sin encabezado.
    df = df.loc[:, [bool(columna) for columna in columnas]].copy()

    if df.columns.duplicated().any():
        raise ValueError(
            "El reporte tiene encabezados repetidos."
        )
    
    for columna in df.columns:
        df[columna] = df[columna].str.strip()

    columna_estado = next(
        columna
        for columna in df.columns
        if normalizar_texto(columna) == "estado actual"
    )

    activos = df[
        df[columna_estado].map(normalizar_texto) == "activo"
    ].copy()

    # Elimina únicamente filas iguales en todas las columnas.
    limpios = activos.drop_duplicates().reset_index(drop=True)
    duplicados = len(activos) - len(limpios)

    with pd.ExcelWriter(
        ruta_destino,
        engine="openpyxl",
    ) as writer:
        limpios.to_excel(
            writer,
            sheet_name="Activos",
            index=False,
        )

        hoja = writer.sheets["Activos"]
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions

        for celdas in hoja.columns:
            ancho = max(
                len(str(celda.value or ""))
                for celda in celdas
            )

            hoja.column_dimensions[
                celdas[0].column_letter
            ].width = min(max(ancho + 2, 12), 45)

    return {
        "registros_activos": len(limpios),
        "duplicados_eliminados": duplicados,
    }



# 6. EJECUTAR LA AUTOMATIZACIÓN


def ejecutar_scraping_reportes(
    usuario,
    contrasena,
    fecha_inicio,
    fecha_termino,
    carpeta_descargas,
):
    """
    Extrae el reporte de WebLun y genera un Excel
    con registros activos sin filas completamente iguales.
    """
    if not usuario or not contrasena:
        raise ValueError(
            "Configure las credenciales de WebLun en el archivo .env."
        )
    
    inicio, termino = validar_fechas(
        fecha_inicio,
        fecha_termino,
    )
    
    carpeta = Path(carpeta_descargas).resolve() / uuid4().hex
    carpeta.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1280, "height": 800},
            )

            page = context.new_page()
            page.set_default_timeout(30000)

            # Espera reutilizable para las capas de carga.
            def esperar_carga(nombre_captura):
                print("Esperando que WebLun termine de cargar...")

                try:
                    page.locator(
                        ".backdrop:visible"
                    ).first.wait_for(
                        state="hidden",
                        timeout=120000,
                    )

                except PlaywrightTimeoutError:
                    ruta_error = carpeta / nombre_captura

                    try:
                        page.screenshot(
                            path=str(ruta_error),
                            full_page=True,
                            mask=[
                                page.locator(
                                    'input[name="loginUsuario"]'
                                ),
                                page.locator(
                                    'input[name="loginContrasena"]'
                                ),
                            ],
                        )

                        print("Captura de diagnóstico:", ruta_error)

                    except Exception as error_captura:
                        print(
                            "No se pudo guardar la captura:",
                            type(error_captura).__name__,
                        )

                    raise RuntimeError(
                        "La capa de carga de WebLun "
                        "no desapareció en 2 minutos."
                    ) from None
                
            # 1. Abrir WebLun.
            print("1. Abriendo WebLun...")

            respuesta = page.goto(
                "https://weblun.rayensalud.cl/",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if respuesta and respuesta.status >= 400:
                raise RuntimeError(
                    f"WebLun respondió con HTTP {respuesta.status}."
                )
            
            page.get_by_text(
                "Ingresar",
                exact=True,
            ).click()

            # 2. Iniciar sesión.
            print("2. Ingresando con la cuenta de WebLun...")

            campo_usuario = page.locator(
                'input[name="loginUsuario"]'
            )
            campo_password = page.locator(
                'input[name="loginContrasena"]'
            )

            campo_usuario.wait_for(
                state="visible",
                timeout=60000,
            )

            campo_usuario.fill(usuario)
            campo_password.fill(contrasena)

            page.get_by_role(
                "button",
                name="Iniciar",
                exact=True,
            ).click()

            menu_reportes = page.get_by_text(
                "Reportes",
                exact=True,
            )

            try:
                menu_reportes.wait_for(
                    state="visible",
                    timeout=60000,
                )

            except PlaywrightTimeoutError:
                ruta_error = carpeta / "error_inicio_sesion.png"

                try:
                    page.screenshot(
                        path=str(ruta_error),
                        full_page=True,
                        mask=[campo_usuario, campo_password],
                    )

                    print("Captura de diagnóstico:", ruta_error)

                except Exception as error_captura:
                    print(
                        "No se pudo guardar la captura:",
                        type(error_captura).__name__,
                    )

                raise RuntimeError(
                    "No se confirmó el inicio de sesión en WebLun."
                ) from None
            
            # 3. Esperar antes de abrir el menú Reportes.
            print("3. Abriendo Reportes...")

            esperar_carga("carga_antes_reportes.png")
            menu_reportes.click(timeout=60000)

            opcion_reporte = page.get_by_text(
                "Reporte de uso de licencias asignadas",
                exact=True,
            )

            opcion_reporte.wait_for(
                state="visible",
                timeout=60000,
            )

            # Esperar también antes de abrir la tarjeta.
            esperar_carga("carga_reportes.png")
            opcion_reporte.click(timeout=60000)

            # 4. Diagnosticar el formulario de fechas.
            print("4. Revisando el formulario del reporte...")

            try:
                page.locator("input:visible").first.wait_for(
                    state="visible",
                    timeout=30000,
                )

            except PlaywrightTimeoutError:
                print(
                    "No apareció un input visible "
                    "en la página principal."
                )

            diagnosticar_campos_reporte(page)

            print("Cantidad de frames:", len(page.frames))

            for numero, frame in enumerate(page.frames):
                campos_frame = frame.locator("input").evaluate_all("""
                    elementos => elementos.map(elemento => ({
                        type: elemento.type,
                        id: elemento.id,
                        name: elemento.name,
                        placeholder: elemento.placeholder
                    }))
                """)

                print(
                    f"Campos del frame {numero}:",
                    campos_frame,
                )

            ruta_captura = carpeta / "formulario_reporte.png"

            page.screenshot(
                path=str(ruta_captura),
                full_page=True,
            )

            print("Captura del reporte:", ruta_captura)

            # Completar las fechas.
            campo_inicio = localizar_fecha(
                page,
                "Fecha inicio",
                0,
            )
            campo_termino = localizar_fecha(
                page,
                "Fecha término",
                1,
            )

            completar_fecha(campo_inicio, inicio)
            completar_fecha(campo_termino, termino)

            page.get_by_role("combobox").select_option(
                label="Sólo con login"
            )

            esperar_carga("carga_antes_obtener.png")

            boton_obtener = page.get_by_text(
                "Obtener",
                exact=True,
            )

            boton_obtener.wait_for(
                state="visible",
                timeout=30000,
            )

            boton_obtener.click(timeout=60000)
            
            # 5. Descargar el Excel.
            print("5. Esperando el Excel...")

            boton_excel = page.get_by_text(
                "Excel",
                exact=True,
            )

            boton_excel.wait_for(
                state="visible",
                timeout=120000,
            )

            with page.expect_download(timeout=120000) as evento:
                boton_excel.click()

            descarga = evento.value

            extension = Path(
                descarga.suggested_filename
            ).suffix.lower()

            if extension not in {".xlsx", ".xls"}:
                raise ValueError(
                    "WebLun no descargó un archivo Excel reconocido."
                )
            
            ruta_original = carpeta / f"original{extension}"
            descarga.save_as(str(ruta_original))

        finally:
            browser.close()

    # 6. Procesar el Excel descargado.
    print("6. Filtrando activos y eliminando filas duplicadas...")

    ruta_limpia = carpeta / "Reporte_Rayen_Activos.xlsx"
    resumen = limpiar_excel(ruta_original, ruta_limpia)

    print("Registros activos:", resumen["registros_activos"])
    print("Duplicados eliminados:", resumen["duplicados_eliminados"])
    
    return {
        "ruta": str(ruta_limpia),
        "ruta_original": str(ruta_original),
        "reporte_id": carpeta.name,
        **resumen,
    }
