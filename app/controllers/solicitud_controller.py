from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.controllers.forms import FormularioSolicitud
from app.models.solicitud_model import SolicitudModel

solicitud_bp = Blueprint('solicitud', __name__)

@solicitud_bp.route('/', methods=['GET', 'POST'])
def registrar():
    form = FormularioSolicitud()
    if form.validate_on_submit():
        tipo = form.tipo_solicitud.data
        nombre = form.nombre_completo.data.strip()
        rut = form.rut.data.strip()
        correo = form.correo.data.strip().lower()
        centros = ", ".join(form.centros.data)
        ip_origen = request.headers.get('X-Forwarded-For', request.remote_addr)

        SolicitudModel.crear_solicitud(
            tipo_solicitud=tipo,
            nombre_completo=nombre,
            rut=rut,
            correo=correo,
            centros=centros,
            gestionado_por="Solicitante (Web)",
            ip_origen=ip_origen
        )
        return redirect(url_for('solicitud.exito'))
    
    return render_template('formulario.html', form=form)

@solicitud_bp.route('/exito')
def exito():
    return render_template('exito.html')

# Panel administrativo de solicitudes
@solicitud_bp.route('/panel')
def panel_solicitudes():
    solicitudes = SolicitudModel.obtener_todas()
    return render_template('panel.html', solicitudes=solicitudes)

# Acción para marcar como gestionada
@solicitud_bp.route('/gestionar/<int:solicitud_id>', methods=['POST'])
def gestionar(solicitud_id):
    nombre_admin = request.form.get('nombre_admin', '').strip()
    if not nombre_admin:
        nombre_admin = "Administrador"

    SolicitudModel.marcar_como_gestionada(solicitud_id, nombre_admin)
    flash(f'La solicitud #{solicitud_id} fue gestionada exitosamente por {nombre_admin}.', 'success')
    return redirect(url_for('solicitud.panel_solicitudes'))