from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.controllers.forms import FormularioSolicitud, FormularioLogin
from app.models.solicitud_model import SolicitudModel

solicitud_bp = Blueprint('solicitud', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or session.get('rol') != 'admin':
            flash('Acceso restringido: Inicie sesión como Administrador.', 'warning')
            return redirect(url_for('solicitud.login'))
        return f(*args, **kwargs)
    return decorated_function

# 1. RUTA PÚBLICA: Cualquier usuario crea solicitudes
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

# 2. LOGIN ADMINISTRADOR
@solicitud_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('rol') == 'admin':
        return redirect(url_for('solicitud.panel_solicitudes'))

    form = FormularioLogin()
    if form.validate_on_submit():
        user = SolicitudModel.autenticar_admin(form.usuario.data.strip(), form.password.data)
        if user and user['rol'] == 'admin':
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']
            flash(f'Bienvenido/a {user["nombre"]}', 'success')
            return redirect(url_for('solicitud.panel_solicitudes'))
        flash('Credenciales incorrectas o usuario no autorizado.', 'danger')

    return render_template('login.html', form=form)

@solicitud_bp.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('solicitud.login'))

# 3. RUTAS PROTEGIDAS PARA EL ADMINISTRADOR
@solicitud_bp.route('/panel')
@admin_required
def panel_solicitudes():
    solicitudes = SolicitudModel.obtener_todas()
    return render_template('panel.html', solicitudes=solicitudes, admin_nombre=session.get('nombre'))

@solicitud_bp.route('/gestionar/<int:solicitud_id>', methods=['POST'])
@admin_required
def gestionar(solicitud_id):
    nombre_admin = session.get('nombre', 'Administrador')
    SolicitudModel.marcar_como_gestionada(solicitud_id, nombre_admin)
    flash(f'La solicitud #{solicitud_id} fue gestionada por {nombre_admin}.', 'success')
    return redirect(url_for('solicitud.panel_solicitudes'))