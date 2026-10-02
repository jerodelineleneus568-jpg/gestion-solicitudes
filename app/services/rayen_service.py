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


def normalizar_texto(valor):
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return " ".join(texto.split())


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


def localizar_fecha(page, etiqueta, posicion):
    """Busca por etiqueta o por los dos campos visibles del reporte."""
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

    # Conserva las asociaciones con establecimientos distintos.
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


def diagnosticar_login(page, carpeta, nombre):
    """
    Guarda una captura del ingreso y muestra atributos
    de los campos, sin imprimir sus valores.
    """
    print("URL recibida:", page.url)
    print("Título recibido:", page.title())

    ruta_captura = carpeta / nombre

    page.screenshot(
        path=str(ruta_captura),
        full_page=True,
    )

    print("Captura guardada en:", ruta_captura)

    campos = page.locator("input").evaluate_all("""
        elementos => elementos.map(elemento => ({
            type: elemento.type,
            id: elemento.id,
            name: elemento.name,
            placeholder: elemento.placeholder
        }))
    """)

    print("Campos encontrados:", campos)


def ejecutar_scraping_reportes(
    usuario,
    contrasena,
    fecha_inicio,
    fecha_termino,
    carpeta_descargas,
):
    """
    Inicia sesión sin ventana, descarga el reporte
    y genera un Excel de activos sin filas duplicadas.
    """
    if not usuario or not contrasena:
        raise ValueError(
            "Configure RAYEN_USUARIO y RAYEN_CONTRASENA en .env."
        )

    inicio, termino = validar_fechas(
        fecha_inicio,
        fecha_termino,
    )

    carpeta = (
        Path(carpeta_descargas).resolve()
        / uuid4().hex
    )
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

            print("Abriendo WebLun...")

            respuesta = page.goto(
                "https://weblun.rayensalud.cl/",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Abre el ingreso desde la navegación del sitio.
            page.get_by_text(
                "Ingresar",
                exact=True,
            ).click()
            
            print(
                "Estado HTTP:",
                respuesta.status if respuesta else "Sin respuesta",
            )

            diagnosticar_login(
                page,
                carpeta,
                "antes_login.png",
            )

            print("Buscando el campo Usuario...")

            campo_usuario = page.get_by_placeholder(
                "Usuario",
                exact=True,
            )

            try:
                campo_usuario.wait_for(
                    state="visible",
                    timeout=30000,
                )
            except PlaywrightTimeoutError:
                # Todavía no se han escrito las credenciales.
                try:
                    diagnosticar_login(
                        page,
                        carpeta,
                        "login_no_encontrado.png",
                    )
                except Exception as error:
                    print(
                        "No se pudo completar el diagnóstico:",
                        type(error).__name__,
                    )

                raise RuntimeError(
                    "No se encontró el campo Usuario. "
                    f"Revise las capturas en: {carpeta}"
                ) from None

            campo_usuario.fill(usuario)

            page.get_by_placeholder(
                "Contraseña",
                exact=True,
            ).fill(contrasena)

            page.get_by_role(
                "button",
                name="Iniciar",
                exact=True,
            ).click()

            page.get_by_text(
                "Reportes",
                exact=True,
            ).wait_for(
                state="visible",
                timeout=60000,
            )

            print("Sesión detectada. Abriendo reporte...")

            page.goto(
                "https://weblun.rayensalud.cl/reporte-activo",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.get_by_text(
                "Reporte de uso de licencias asignadas",
                exact=True,
            ).wait_for(
                state="visible",
                timeout=60000,
            )

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

            page.get_by_role(
                "button",
                name=re.compile(r"^\s*Obtener\s*$"),
            ).click()

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
                    "La descarga no tiene un formato Excel reconocido."
                )

            ruta_original = carpeta / f"original{extension}"
            descarga.save_as(str(ruta_original))

            print("Excel descargado.")

        finally:
            browser.close()

    ruta_limpia = carpeta / "Reporte_Rayen_Activos.xlsx"

    resumen = limpiar_excel(
        ruta_original,
        ruta_limpia,
    )

    print("Registros activos:", resumen["registros_activos"])
    print(
        "Duplicados eliminados:",
        resumen["duplicados_eliminados"],
    )

    return {
        "ruta": str(ruta_limpia),
        **resumen,
    }