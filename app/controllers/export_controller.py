import re
from pathlib import Path

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, send_file, session, url_for,
)
from app.models.solicitud_model import SolicitudModel
from app.services.rayen_service import ejecutar_scraping_reportes, validar_fechas

export_bp = Blueprint('export', __name__)


def es_administrador():
    return bool(session.get('user_id')) and session.get('rol') == 'admin'


def carpeta_del_usuario():
    return Path(current_app.config['UPLOAD_FOLDER']).resolve() / 'rayen' / str(int(session['user_id']))


def recuperar_ultimo_reporte():
    archivos = [archivo for archivo in carpeta_del_usuario().glob('*/Reporte_Rayen_Activos.xlsx')
                if archivo.is_file() and re.fullmatch(r'[0-9a-f]{32}', archivo.parent.name)]
    if not archivos:
        return False
    ultimo = max(archivos, key=lambda archivo: archivo.stat().st_mtime)
    if session.get('rayen_reporte_id') != ultimo.parent.name:
        session.pop('rayen_fecha_inicio', None)
        session.pop('rayen_fecha_termino', None)
    session['rayen_reporte_id'] = ultimo.parent.name
    return True


@export_bp.route('/exportar/excel', methods=['GET', 'POST'])
def exportar_excel():
    if not es_administrador():
        flash('Debe iniciar sesión como administrador.', 'warning')
        return redirect(url_for('solicitud.login'))
    fecha_inicio = ''
    fecha_termino = ''
    if request.method == 'POST':
        fecha_inicio = request.form.get('fecha_inicio', '')
        fecha_termino = request.form.get('fecha_termino', '')
        try:
            validar_fechas(fecha_inicio, fecha_termino)

            resultado = ejecutar_scraping_reportes(
                usuario=current_app.config['RAYEN_USUARIO'],
                contrasena=current_app.config['RAYEN_CONTRASENA'],
                fecha_inicio=fecha_inicio,
                fecha_termino=fecha_termino,
                carpeta_descargas=str(carpeta_del_usuario()),
            )
            # Consulta el original: incluye filas que la limpieza de activos descarta.
            actualizadas = SolicitudModel.sincronizar_desde_excel(resultado['ruta_original'])
            session['rayen_reporte_id'] = resultado['reporte_id']
            session['rayen_fecha_inicio'] = fecha_inicio
            session['rayen_fecha_termino'] = fecha_termino
            flash(f'Extracción completada. Se actualizaron {actualizadas} solicitudes.', 'success')
            return redirect(url_for('solicitud.panel_solicitudes'))
        except ValueError as error:
            flash(str(error), 'danger')
        except Exception:
            current_app.logger.exception('Falló la extracción o sincronización desde WebLun.')
            flash('No se pudo completar la extracción y sincronización. Revise la terminal de VS Code.', 'danger')
    return render_template('exportar_rayen.html', fecha_inicio=fecha_inicio, fecha_termino=fecha_termino)


def ruta_reporte_actual():
    reporte_id = session.get('rayen_reporte_id', '')
    if not isinstance(reporte_id, str) or not re.fullmatch(r'[0-9a-f]{32}', reporte_id):
        abort(404)
    ruta = carpeta_del_usuario() / reporte_id / 'Reporte_Rayen_Activos.xlsx'
    if not ruta.is_file():
        abort(404)

    return ruta


@export_bp.route('/rayen/resultado')
def resultado_rayen():
    # Mantiene compatible el botón antiguo y muestra el único panel de solicitudes.
    if not es_administrador():
        return redirect(url_for('solicitud.login'))
    return redirect(url_for('solicitud.panel_solicitudes'))


@export_bp.route('/rayen/descargar')
def descargar_rayen():
    if not es_administrador():
        return redirect(url_for('solicitud.login'))
    if not session.get('rayen_reporte_id') and not recuperar_ultimo_reporte():
        flash('No hay una extracción descargable para este administrador.', 'warning')
        return redirect(url_for('export.exportar_excel'))
    return send_file(
        str(ruta_reporte_actual()),
        download_name='Reporte_Rayen_Activos.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
