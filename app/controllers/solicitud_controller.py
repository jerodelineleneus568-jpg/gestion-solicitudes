from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.controllers.forms import FormularioSolicitud, FormularioLogin
from app.models.solicitud_model import SolicitudModel, limpiar_rut
from flask import current_app
# 1. Definición del Blueprint (debe ir antes de cualquier @solicitud_bp.route)
solicitud_bp = Blueprint('solicitud', __name__)

# 2. Decorador de autenticación de administradores
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or session.get('rol') != 'admin':
            flash("Debe iniciar sesión como administrador para acceder.", "warning")
            return redirect(url_for('solicitud.login'))
        return f(*args, **kwargs)
    return decorated_function

# 3. Formulario principal para crear solicitudes
@solicitud_bp.route('/', methods=['GET', 'POST'])
def registrar():
    form = FormularioSolicitud()
    if form.validate_on_submit():
        tipo = form.tipo_solicitud.data
        sistema = form.sistema.data
        nombre = form.nombre_completo.data.strip()
        rut = form.rut.data.strip()
        rut_clean = limpiar_rut(rut)
        correo = form.correo.data.strip().lower()
        centros = ", ".join(form.centros.data)
        ip_origen = request.headers.get('X-Forwarded-For', request.remote_addr)

        # 1. Comprobar si ya tiene solicitud histórica para este sistema
        solicitud_existente = SolicitudModel.existe_solicitud_para_sistema(rut_clean, sistema)
        if solicitud_existente:
            nombre_registrado = (solicitud_existente['nombre_completo'] or '').strip()

            # Verificar si el nombre coincide

            if nombre_registrado and nombre.lower() != nombre_registrado.lower():
                flash(
                    f"El RUT {rut} ya se encuentra registrado a nombre de '{nombre_registrado}'. "
                    f"Verifique los datos ingresados.",
                    "danger"
                )
                return render_template('formulario.html', form=form)
            
            estado_actual = solicitud_existente['estado']
            admin_responsable = solicitud_existente['gestionado_por_admin'] or "Administrador"
            fecha_g = solicitud_existente['fecha_gestion'] or ""

            if estado_actual == 'Gestionada':
                flash(
                    f"Tu solicitud para el sistema {sistema} ya fue GESTIONADA con éxito por {admin_responsable} el {fecha_g}. "
                    f"Tu cuenta ya se encuentra procesada.",
                    "success"
                )
            else:
                flash(
                    f"Tu solicitud para el sistema {sistema} ya fue enviada y se encuentra actualmente PENDIENTE de revisión.",
                    "warning"
                )
            return render_template('formulario.html', form=form)
        
        # 2. Registrar la solicitud si no existe duplicidad
        try:
            SolicitudModel.crear_solicitud(
                tipo_solicitud=tipo,
                sistema=sistema,
                nombre_completo=nombre,
                rut=rut,
                correo=correo,
                centros=centros,
                gestionado_por="Solicitante (Web)",
                ip_origen=ip_origen
            )
        except Exception:
            current_app.logger.exception('No se pudo registrar la solicitud y consultar el Excel.')
            flash(
                'No se pudo registrar la solicitud. Administración debe revisar '
                'el Excel de sincronización antes de volver a intentarlo.',
                'danger',
            )
            return render_template('formulario.html', form=form)

        flash(f"¡Solicitud para el sistema {sistema} enviada con éxito!", "success")
        return redirect(url_for('solicitud.exito', sistema=sistema))
    
    return render_template('formulario.html', form=form)

# 4. Pantalla de éxito tras el registro
@solicitud_bp.route('/exito/<sistema>')
def exito(sistema):
    return render_template('exito.html', sistema=sistema)

# 5. Consulta pública de estado por RUT
@solicitud_bp.route('/consultar', methods=['GET', 'POST'])
def consultar_estado():
    solicitudes = None
    rut_buscado = ""
    if request.method == 'POST':
        rut_buscado = request.form.get('rut', '').strip()
        if rut_buscado:
            solicitudes = SolicitudModel.obtener_por_rut(rut_buscado)
            if not solicitudes:
                flash(f"No se encontraron solicitudes registradas para el RUT {rut_buscado}.", "warning")
        else:
            flash("Por favor ingrese un RUT para realizar la consulta.", "danger")

    return render_template('consultar.html', solicitudes=solicitudes, rut_buscado=rut_buscado)

# 6. Panel de administración
@solicitud_bp.route('/panel')
@admin_required
def panel_solicitudes():
    return render_template(
        'panel.html',
        solicitudes=SolicitudModel.obtener_todas(),
        admin_nombre=session.get('nombre', 'Administrador'),
        reporte_weblun=SolicitudModel.obtener_reporte_actual(),
        parametros_pasivacion=SolicitudModel.obtener_configuracion_pasivacion(),
    )

# 7. Marcar como gestionada manualmente
@solicitud_bp.route('/gestionar/<int:solicitud_id>', methods=['POST'])
@admin_required
def gestionar(solicitud_id):
    nombre_admin = session.get('nombre', 'Administrador')
    SolicitudModel.marcar_como_gestionada(solicitud_id, nombre_admin)
    flash(f"Solicitud #{solicitud_id} marcada como Gestionada.", "success")
    return redirect(url_for('solicitud.panel_solicitudes'))

# 8. Eliminar solicitud
@solicitud_bp.route('/eliminar/<int:solicitud_id>', methods=['POST'])
@admin_required
def eliminar(solicitud_id):
    SolicitudModel.eliminar_solicitud(solicitud_id)
    flash(f"La solicitud #{solicitud_id} ha sido eliminada.", "info")
    return redirect(url_for('solicitud.panel_solicitudes'))


@solicitud_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('rol') == 'admin':
        return redirect(url_for('solicitud.panel_solicitudes'))
    
    form = FormularioLogin()
    if form.validate_on_submit():
        # Cambiado a form.usuario.data
        user = SolicitudModel.autenticar_admin(form.usuario.data.strip(), form.password.data)
        if user:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']
            flash(f"Bienvenido/a {user['nombre']}.", "success")
            return redirect(url_for('solicitud.panel_solicitudes'))
        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template('login.html', form=form)

@solicitud_bp.route('/logout')
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for('solicitud.login'))


@solicitud_bp.route('/pasivacion')
@admin_required
def panel_pasivacion():
    from app.services.pasivacion_service import calcular_reporte_pasivacion, fecha_hoy_chile
    parametros = SolicitudModel.obtener_configuracion_pasivacion()
    hoy = fecha_hoy_chile()
    filas = []
    resumen = {'total': 0, 'Puede pasivarse': 0, 'No pasivar': 0, 'Revisar': 0}
    # Referencia institucional: la misma que usan las nuevas solicitudes.
    with SolicitudModel.conexion() as conn:
        registro = conn.execute(
            'SELECT ruta_excel, fecha_sincronizacion FROM reporte_weblun_actual WHERE id = 1'
        ).fetchone()
        reporte = dict(registro) if registro else None
    if reporte:
        try:
            filas, resumen = calcular_reporte_pasivacion(
                reporte['ruta_excel'], hoy,
                umbral_login=parametros['dias_sin_login'],
                umbral_movimiento=parametros['dias_sin_movimiento'],
            )
        except ValueError as error:
            flash(str(error), 'warning')
        except Exception:
            current_app.logger.exception('No se pudo calcular el reporte de pasivación.')
            flash('No se pudo leer el reporte de pasivación. Revise la terminal.', 'danger')
    return render_template(
        'pasivacion.html', filas=filas, resumen=resumen, reporte=reporte,
        fecha_evaluacion=hoy.strftime('%d/%m/%Y'), parametros=parametros,
    )


@solicitud_bp.route('/pasivacion/configuracion', methods=['GET', 'POST'])
@admin_required
def configurar_pasivacion():
    parametros = SolicitudModel.obtener_configuracion_pasivacion()
    valores = dict(parametros)
    if request.method == 'POST':
        valores['dias_sin_login'] = request.form.get('dias_sin_login', '')
        valores['dias_sin_movimiento'] = request.form.get('dias_sin_movimiento', '')
        try:
            SolicitudModel.guardar_configuracion_pasivacion(
                valores['dias_sin_login'], valores['dias_sin_movimiento'],
                session.get('nombre', 'Administrador'),
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('configuracion_pasivacion.html', parametros=parametros, valores=valores), 400
        except Exception:
            current_app.logger.exception('No se pudieron guardar los parámetros de pasivación.')
            flash('No se pudo guardar la configuración. Revise la terminal.', 'danger')
            return render_template('configuracion_pasivacion.html', parametros=parametros, valores=valores), 500
        flash('Reglas guardadas. La evaluación usará los nuevos valores.', 'success')
        return redirect(url_for('solicitud.panel_pasivacion'))
    return render_template('configuracion_pasivacion.html', parametros=parametros, valores=valores)
