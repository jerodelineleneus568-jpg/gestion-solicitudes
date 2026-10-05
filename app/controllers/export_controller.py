import re
from pathlib import Path

import pandas as pd
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from app.services.rayen_service import (
    ejecutar_scraping_reportes,
    validar_fechas,
)


export_bp = Blueprint("export", __name__)


def es_administrador():
    return (
        bool(session.get("user_id"))
        and session.get("rol") == "admin"
    )


def carpeta_del_usuario():
    usuario_id = int(session["user_id"])

    return (
        Path(current_app.config["UPLOAD_FOLDER"]).resolve()
        / "rayen"
        / str(usuario_id)
    )


def recuperar_ultimo_reporte():
    carpeta = carpeta_del_usuario()

    archivos = [
        archivo
        for archivo in carpeta.glob(
            "*/Reporte_Rayen_Activos.xlsx"
        )
        if archivo.is_file()
        and re.fullmatch(r"[0-9a-f]{32}", archivo.parent.name)
    ]

    if not archivos:
        return False

    ultimo = max(
        archivos,
        key=lambda archivo: archivo.stat().st_mtime,
    )

    if session.get("rayen_reporte_id") != ultimo.parent.name:
        session.pop("rayen_fecha_inicio", None)
        session.pop("rayen_fecha_termino", None)

    session["rayen_reporte_id"] = ultimo.parent.name
    return True

@export_bp.route("/exportar/excel", methods=["GET", "POST"])
def exportar_excel():
    if not es_administrador():
        flash(
            "Debe iniciar sesión como administrador.",
            "warning",
        )
        return redirect(url_for("solicitud.login"))

    fecha_inicio = ""
    fecha_termino = ""

    if request.method == "POST":
        fecha_inicio = request.form.get("fecha_inicio", "")
        fecha_termino = request.form.get("fecha_termino", "")

        try:
            validar_fechas(fecha_inicio, fecha_termino)

            resultado = ejecutar_scraping_reportes(
                usuario=current_app.config["RAYEN_USUARIO"],
                contrasena=current_app.config["RAYEN_CONTRASENA"],
                fecha_inicio=fecha_inicio,
                fecha_termino=fecha_termino,
                carpeta_descargas=str(carpeta_del_usuario()),
            )

            # Guarda solo el identificador del resultado en sesión.
            session["rayen_reporte_id"] = resultado["reporte_id"]
            session["rayen_fecha_inicio"] = fecha_inicio
            session["rayen_fecha_termino"] = fecha_termino

            return redirect(url_for("export.resultado_rayen"))

        except ValueError as error:
            flash(str(error), "danger")

        except Exception:
            current_app.logger.exception(
                "Falló la extracción desde WebLun."
            )
            flash(
                "No se pudo completar la extracción. "
                "Revise el error en la terminal de VS Code.",
                "danger",
            )

    return render_template(
        "exportar_rayen.html",
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_termino,
    )


def ruta_reporte_actual():
    reporte_id = session.get("rayen_reporte_id", "")

    if not isinstance(reporte_id, str) or not re.fullmatch(
        r"[0-9a-f]{32}",
        reporte_id,
    ):
        abort(404)

    ruta = (
        carpeta_del_usuario()
        / reporte_id
        / "Reporte_Rayen_Activos.xlsx"
    )

    if not ruta.is_file():
        abort(404)

    return ruta


@export_bp.route("/rayen/resultado")
def resultado_rayen():
    if not es_administrador():
        return redirect(url_for("solicitud.login"))

    if not session.get("rayen_reporte_id"):
        if not recuperar_ultimo_reporte():
            flash(
                "Todavía no hay una extracción guardada "
                "para este administrador.",
                "warning",
            )
            return redirect(url_for("export.exportar_excel"))

    ruta = ruta_reporte_actual()

    df = pd.read_excel(
        ruta,
        dtype=str,
        keep_default_na=False,
    )

    return render_template(
        "resultado_rayen.html",
        columnas=list(df.columns),
        registros=df.to_dict(orient="records"),
        total=len(df),
        fecha_inicio=session.get("rayen_fecha_inicio", ""),
        fecha_termino=session.get("rayen_fecha_termino", ""),
    )


@export_bp.route("/rayen/descargar")
def descargar_rayen():
    if not es_administrador():
        return redirect(url_for("solicitud.login"))

    ruta = ruta_reporte_actual()

    return send_file(
        str(ruta),
        download_name="Reporte_Rayen_Activos.xlsx",
        as_attachment=True,
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )