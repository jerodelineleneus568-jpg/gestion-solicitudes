from functools import wraps
from flask import render_template, redirect, url_for, flash, session
from app.services.rayen_service import ejecutar_scraping_reportes
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.controllers.forms import FormularioSolicitud, FormularioLogin
from app.models.solicitud_model import SolicitudModel, limpiar_rut
import os
import json
from werkzeug.utils import secure_filename
# 1. Definición del Blueprint (debe ir antes de cualquier @solicitud_bp.route)
solicitud_bp = Blueprint('solicitud', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 2. Decorador de autenticación de administradores
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('rol') != 'admin':
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
    solicitudes = SolicitudModel.obtener_todas()
    admin_nombre = session.get('nombre', 'Administrador')
    return render_template('panel.html', solicitudes=solicitudes, admin_nombre=admin_nombre)

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


# 9. Importar reporte oficial (Excel/CSV descargado)
@solicitud_bp.route('/importar-reporte', methods=['POST'])
@admin_required
def importar_reporte():
    if 'archivo' not in request.files:
        flash("No se seleccionó ningún archivo.", "danger")
        return redirect(url_for('solicitud.panel_solicitudes'))

    file = request.files['archivo']
    sistema_reporte = request.form.get('sistema_reporte', 'Rayen').strip()

    if file.filename == '' or not allowed_file(file.filename):
        flash("Formato no válido. Debe ser un archivo Excel (.xlsx, .xls) o CSV.", "danger")
        return redirect(url_for('solicitud.panel_solicitudes'))

    try:
        filename = secure_filename(file.filename)
        ruta_archivo = os.path.join(UPLOAD_FOLDER, f"ultimo_reporte_{sistema_reporte.lower()}.xlsx")
        file.save(ruta_archivo)

        # Detectar cabecera dinámica
        df = None
        for h_row in [1, 0, 2]:
            try:
                temp_df = pd.read_excel(ruta_archivo, header=h_row)
                cols = [str(c).strip().lower() for c in temp_df.columns]
                if any(k in cols for k in ['run', 'rut']):
                    temp_df.columns = cols
                    df = temp_df
                    break
            except Exception:
                continue

        if df is None:
            raw_df = pd.read_excel(ruta_archivo, header=None)
            for idx, row in raw_df.iterrows():
                row_vals = [str(v).strip().lower() for v in row.values]
                if 'run' in row_vals or 'rut' in row_vals:
                    df = raw_df.iloc[idx+1:].copy()
                    df.columns = row_vals
                    break

        if df is None:
            flash("No se encontró la columna de RUT/RUN en el archivo cargado.", "danger")
            return redirect(url_for('solicitud.panel_solicitudes'))

        col_rut = next((c for c in df.columns if c in ['run', 'rut'] or 'run' in c or 'rut' in c), None)
        col_fecha = next((c for c in df.columns if any(k in c for k in ['último login', 'ultimo login', 'login', 'fecha'])), None)

        total_procesados = 0
        admin_actual = session.get('nombre', 'Administrador')

        for _, row in df.iterrows():
            val_rut = str(row[col_rut]).strip()
            val_fecha = str(row[col_fecha]) if col_fecha and pd.notna(row[col_fecha]) else None

            if val_rut and val_rut.lower() not in ['nan', '', 'none']:
                actualizados = SolicitudModel.actualizar_desde_reporte(
                    rut=val_rut,
                    sistema=sistema_reporte,
                    fecha_movimiento=val_fecha,
                    admin_nombre=f"Reporte ({admin_actual})"
                )
                total_procesados += actualizados

        flash(f"Reporte de {sistema_reporte} cargado correctamente. Se conciliarion {total_procesados} solicitudes pendientes.", "success")
        return redirect(url_for('solicitud.ver_reporte', sistema=sistema_reporte))

    except Exception as e:
        flash(f"Ocurrió un error al procesar el archivo: {str(e)}", "danger")
    return redirect(url_for('solicitud.panel_solicitudes'))


@solicitud_bp.route('/reporte/<sistema>')
@admin_required
def ver_reporte(sistema):
    """Muestra la tabla interactiva de los datos del Excel cargado."""
    ruta_archivo = os.path.join(UPLOAD_FOLDER, f"ultimo_reporte_{sistema.lower()}.xlsx")
    
    if not os.path.exists(ruta_archivo):
        flash(f"Aún no se ha subido ningún reporte para {sistema}.", "info")
        return redirect(url_for('solicitud.panel_solicitudes'))

    try:
        # Leer el Excel para mostrarlo en tabla
        df = None
        for h in [1, 0, 2]:
            try:
                temp = pd.read_excel(ruta_archivo, header=h)
                cols_lower = [str(c).strip().lower() for c in temp.columns]
                if any('run' in c or 'rut' in c for c in cols_lower):
                    df = temp
                    break
            except Exception:
                continue

        if df is None:
            df = pd.read_excel(ruta_archivo)

        # Reemplazar NaN por texto vacío para HTML limpio
        df = df.fillna('')
        
        columnas = list(df.columns)
        registros = df.to_dict(orient='records')
        total_filas = len(registros)

        return render_template('ver_reporte.html', 
                               sistema=sistema, 
                               columnas=columnas, 
                               registros=registros, 
                               total_filas=total_filas)
    except Exception as e:
        flash(f"Error al leer el archivo guardado: {str(e)}", "danger")
    return redirect(url_for('solicitud.panel_solicitudes'))

# 10. Login y Logout
@solicitud_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('rol') == 'admin':
        return redirect(url_for('solicitud.panel_solicitudes'))

    form = FormularioLogin()
    if form.validate_on_submit():
        # Cambiado a form.usuario.data
        user = SolicitudModel.autenticar_admin(form.usuario.data.strip(), form.password.data)
        if user:
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

@solicitud_bp.route('/sincronizar-api-rayen', methods=['POST'])
@admin_required
def sincronizar_api_rayen():
    return redirect(url_for('export.exportar_excel'))