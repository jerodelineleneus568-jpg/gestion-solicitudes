from flask import (
    Blueprint,
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


@export_bp.route("/exportar/excel", methods=["GET", "POST"])
def exportar_excel():
    if (
        not session.get("user_id")
        or session.get("rol") != "admin"
    ):
        flash(
            "Debe iniciar sesión como administrador.",
            "warning",
        )
        return redirect(url_for("solicitud.login"))

    if request.method == "GET":
        return render_template("exportar_rayen.html")

    fecha_inicio = request.form.get("fecha_inicio", "")
    fecha_termino = request.form.get("fecha_termino", "")

    try:
        validar_fechas(fecha_inicio, fecha_termino)

        resultado = ejecutar_scraping_reportes(
            usuario=current_app.config["RAYEN_USUARIO"],
            contrasena=current_app.config["RAYEN_CONTRASENA"],
            fecha_inicio=fecha_inicio,
            fecha_termino=fecha_termino,
            carpeta_descargas=current_app.config["UPLOAD_FOLDER"],
        )

        return send_file(
            resultado["ruta"],
            download_name=(
                f"Rayen_Activos_{fecha_inicio}_{fecha_termino}.xlsx"
            ),
            as_attachment=True,
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    except ValueError as error:
        flash(str(error), "danger")

    except Exception:
        current_app.logger.exception(
            "Falló la descarga automática del reporte Rayen."
        )
        flash(
            "No se pudo descargar el reporte. "
            "Revise el error en la terminal de VS Code.",
            "danger",
        )

    return render_template(
        "exportar_rayen.html",
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_termino,
    )