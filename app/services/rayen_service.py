import calendar
import re
import unicodedata
from datetime import date
from pathlib import Path
from uuid import uuid4

import pandas as pd
from playwright.sync_api import sync_playwright


def normalizar_texto(valor):
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.split())


def validar_fechas(fecha_inicio, fecha_termino):
    """Recibe fechas del formulario en formato AAAA-MM-DD."""
    try:
        inicio = date.fromisoformat(fecha_inicio)
        termino = date.fromisoformat(fecha_termino)
    except (TypeError, ValueError):
        raise ValueError("Ingrese ambas fechas correctamente.") from None

    if inicio > termino:
        raise ValueError(
            "La fecha de inicio no puede ser posterior a la de término."
        )

    # Límite de un mes calendario.
    mes_siguiente = inicio.month % 12 + 1
    anio_siguiente = inicio.year + (inicio.month == 12)
    ultimo_dia = calendar.monthrange(
        anio_siguiente, mes_siguiente
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
    """
    Primero busca el campo por su etiqueta.
    Si la etiqueta no está asociada al input, usa los dos
    campos visibles del formulario de reporte.
    """
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
            f"No se pudo identificar '{etiqueta}'. "
            "Es necesario revisar el selector del campo."
        )

    return campos.nth(posicion)


def completar_fecha(campo, fecha):
    # Los inputs date reciben AAAA-MM-DD.
    # En tus capturas los campos muestran DD-MM-AAAA.
    formato = (
        fecha.isoformat()
        if campo.get_attribute("type") == "date"
        else fecha.strftime("%d-%m-%Y")
    )

    campo.fill(formato)
    campo.press("Tab")


def limpiar_excel(ruta_original, ruta_destino):
    """
    Detecta la cabecera, conserva Estado actual = Activo
    y elimina filas iguales en todas sus columnas.
    """
    tabla = pd.read_excel(
        ruta_original,
        header=None,
        dtype=str,
        keep_default_na=False,
    )

    indice_cabecera = None

    for indice, fila in tabla.head(30).iterrows():
        nombres = [normalizar_texto(v) for v in fila]

        if (
            ("run" in nombres or "rut" in nombres)
            and "estado actual" in nombres
        ):
            indice_cabecera = indice
            break

    if indice_cabecera is None:
        raise ValueError(
            "El Excel no contiene una cabecera con RUN/RUT "
            "y Estado actual."
        )

    columnas = [
        " ".join(str(v).split())
        for v in tabla.loc[indice_cabecera]
    ]

    df = tabla.loc[indice_cabecera + 1:].copy()
    df.columns = columnas

    # Descarta columnas sin encabezado.
    df = df.loc[:, [bool(c) for c in columnas]].copy()

    if df.columns.duplicated().any():
        raise ValueError(
            "El reporte tiene encabezados repetidos. "
            "Revise su estructura antes de procesarlo."
        )

    for columna in df.columns:
        df[columna] = df[columna].str.strip()

    columna_estado = next(
        c for c in df.columns
        if normalizar_texto(c) == "estado actual"
    )

    activos = df[
        df[columna_estado].map(normalizar_texto) == "activo"
    ].copy()

    cantidad_activos = len(activos)
    limpios = activos.drop_duplicates().reset_index(drop=True)
    duplicados = cantidad_activos - len(limpios)

    with pd.ExcelWriter(ruta_destino, engine="openpyxl") as writer:
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


def ejecutar_scraping_reportes(
    fecha_inicio,
    fecha_termino,
    carpeta_descargas,
):
    """
    Abre WebLun en el escritorio de Ubuntu.
    Espera el inicio de sesión manual y descarga el reporte.
    """
    import os
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "La aplicación debe iniciarse desde una terminal "
            "del escritorio remoto de Ubuntu."
        )

    inicio, termino = validar_fechas(
        fecha_inicio,
        fecha_termino,
    )

    carpeta = Path(carpeta_descargas) / uuid4().hex
    carpeta.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
        )

        try:
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 1280, "height": 800},
            )

            page = context.new_page()
            page.set_default_timeout(30000)

            page.goto(
                "https://weblun.rayensalud.cl/login",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print(
                "WebLun está abierto en el escritorio remoto. "
                "Ingrese sus credenciales y presione Iniciar. "
                "Tiene 5 minutos."
            )

            # No escribe usuario ni contraseña.
            # Espera el menú que aparece después de iniciar sesión.
            try:
                page.get_by_text(
                    "Reportes",
                    exact=True,
                ).wait_for(
                    state="visible",
                    timeout=300000,
                )

            except PlaywrightTimeoutError:
                raise ValueError(
                    "No se detectó el inicio de sesión en 5 minutos. "
                    "Vuelva a intentarlo desde la aplicación."
                ) from None

            print("Sesión detectada. Consultando el reporte...")

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

            print("Reporte descargado correctamente.")

        finally:
            browser.close()

    ruta_limpia = carpeta / "Reporte_Rayen_Activos.xlsx"

    resumen = limpiar_excel(
        ruta_original,
        ruta_limpia,
    )

    print(
        f"Registros activos: {resumen['registros_activos']}. "
        f"Duplicados eliminados: "
        f"{resumen['duplicados_eliminados']}."
    )

    return {
        "ruta": str(ruta_limpia),
        **resumen,
    }