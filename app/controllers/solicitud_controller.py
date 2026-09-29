from flask import Blueprint, render_template, request, redirect, url_for
from app.controllers.forms import FormularioSolicitud
from app.models.solicitud_model import SolicitudModel

solicitud_bp = Blueprint('solicitud', __name__)

@solicitud_bp.route('/', methods=['GET', 'POST'])
def registrar():
    form = FormularioSolicitud()
    if form.validate_on_submit():
        tipo = form.tipo_solicitud.data
        nombre = form.nombre_completo.data.strip()
        rut = form.rut.data.replace(".", "").strip().upper()
        correo = form.correo.data.strip().lower()
        centros = ", ".join(form.centros.data)
        gestionado = form.gestionado_por.data.strip()
        ip_origen = request.headers.get('X-Forwarded-For', request.remote_addr)

        SolicitudModel.crear_solicitud(
            tipo_solicitud=tipo,
            nombre_completo=nombre,
            rut=rut,
            correo=correo,
            centros=centros,
            gestionado_por=gestionado,
            ip_origen=ip_origen
        )
        return redirect(url_for('solicitud.exito'))
    
    return render_template('formulario.html', form=form)

@solicitud_bp.route('/exito')
def exito():
    return render_template('exito.html')