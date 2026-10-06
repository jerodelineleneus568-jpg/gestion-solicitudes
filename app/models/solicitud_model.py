import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash
from app.config import Config
from app.services.reporte_weblun_service import leer_indice_reporte, datos_para_solicitud


def limpiar_rut(rut_texto):
    
    if not rut_texto:
        return ''
    return re.sub(r'[^0-9kK]', '', str(rut_texto)).upper()


class SolicitudModel:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    @contextmanager
    def conexion(cls):
        conn = cls.get_connection()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @classmethod
    def init_db(cls):
        with cls.conexion() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS solicitudes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_solicitud TEXT NOT NULL,
                sistema TEXT NOT NULL DEFAULT 'Rayen',
                nombre_completo TEXT NOT NULL,
                rut TEXT NOT NULL,
                correo TEXT NOT NULL,
                centros TEXT NOT NULL,
                gestionado_por TEXT NOT NULL,
                ip_origen TEXT,
                estado TEXT DEFAULT 'Pendiente',
                gestionado_por_admin TEXT DEFAULT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_gestion TIMESTAMP DEFAULT NULL,
                ultimo_login TEXT DEFAULT NULL,
                ultimo_movimiento TEXT DEFAULT NULL,
                estado_registro_weblun TEXT NOT NULL DEFAULT 'Sin reporte disponible'
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nombre TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'admin'
            )''')
            if not conn.execute("SELECT id FROM usuarios WHERE username = 'admin'").fetchone():
                conn.execute('INSERT INTO usuarios (username, password_hash, nombre, rol) VALUES (?, ?, ?, ?)',
                             ('admin', generate_password_hash('Admin2026!'), 'Administrador del Sistema', 'admin'))
            columnas = {fila['name'] for fila in conn.execute('PRAGMA table_info(solicitudes)')}
            migraciones = {
                'sistema': "TEXT NOT NULL DEFAULT 'Rayen'",
                'estado': "TEXT DEFAULT 'Pendiente'",
                'gestionado_por_admin': 'TEXT DEFAULT NULL',
                'fecha_gestion': 'TIMESTAMP DEFAULT NULL',
                'ultimo_login': 'TEXT DEFAULT NULL',
                'ultimo_movimiento': 'TEXT DEFAULT NULL',
                'estado_registro_weblun': "TEXT NOT NULL DEFAULT 'Sin reporte disponible'",
            }
            for nombre, definicion in migraciones.items():
                if nombre not in columnas:
                    conn.execute(f'ALTER TABLE solicitudes ADD COLUMN {nombre} {definicion}')
            # Solo conserva la referencia interna al Excel oficial de esta institución.
            conn.execute('''CREATE TABLE IF NOT EXISTS reporte_weblun_actual (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ruta_excel TEXT NOT NULL,
                fecha_sincronizacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.execute('''UPDATE solicitudes SET estado_registro_weblun = 'No corresponde (Iris)'
                WHERE LOWER(TRIM(sistema)) != 'rayen'
                AND estado_registro_weblun = 'Sin reporte disponible' ''')

    @classmethod
    def crear_solicitud(cls, tipo_solicitud, sistema, nombre_completo, rut, correo, centros, gestionado_por, ip_origen):
        with cls.conexion() as conn:
            # Serializa el registro con la publicación de una nueva sincronización.
            conn.execute('BEGIN IMMEDIATE')
            reporte = conn.execute('SELECT ruta_excel FROM reporte_weblun_actual WHERE id = 1').fetchone()
            indice = None
            if reporte and sistema.strip().lower() == 'rayen':
                indice = leer_indice_reporte(reporte['ruta_excel'])
            login, movimiento, existencia = datos_para_solicitud(rut, sistema, indice)
            cursor = conn.execute('''INSERT INTO solicitudes (
                tipo_solicitud, sistema, nombre_completo, rut, correo, centros,
                gestionado_por, ip_origen, estado, ultimo_login,
                ultimo_movimiento, estado_registro_weblun
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?, ?)''',
                (tipo_solicitud, sistema, nombre_completo, rut, correo, centros,
                 gestionado_por, ip_origen, login, movimiento, existencia))
            return cursor.lastrowid

    @classmethod
    def sincronizar_desde_excel(cls, ruta_excel):
        ruta = str(Path(ruta_excel).resolve())
        # Validar todo antes de modificar la base de datos.
        indice = leer_indice_reporte(ruta)
        with cls.conexion() as conn:
            conn.execute('BEGIN IMMEDIATE')
            solicitudes = conn.execute('SELECT id, rut, sistema FROM solicitudes').fetchall()
            for solicitud in solicitudes:
                datos = datos_para_solicitud(solicitud['rut'], solicitud['sistema'], indice)
                conn.execute('''UPDATE solicitudes SET ultimo_login = ?, ultimo_movimiento = ?,
                    estado_registro_weblun = ? WHERE id = ?''', (*datos, solicitud['id']))
            conn.execute('''INSERT INTO reporte_weblun_actual (id, ruta_excel)
                VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET
                ruta_excel = excluded.ruta_excel, fecha_sincronizacion = CURRENT_TIMESTAMP''', (ruta,))
            return len(solicitudes)

    @classmethod
    def obtener_reporte_actual(cls):
        with cls.conexion() as conn:
            fila = conn.execute('SELECT fecha_sincronizacion FROM reporte_weblun_actual WHERE id = 1').fetchone()
            return dict(fila) if fila else None

    @classmethod
    def obtener_todas(cls):
        with cls.conexion() as conn:
            return conn.execute('SELECT * FROM solicitudes ORDER BY fecha_creacion DESC, id DESC').fetchall()

    @classmethod
    def marcar_como_gestionada(cls, solicitud_id, nombre_admin):
        with cls.conexion() as conn:
            conn.execute('''UPDATE solicitudes SET estado = 'Gestionada', gestionado_por_admin = ?,
                fecha_gestion = CURRENT_TIMESTAMP WHERE id = ?''', (nombre_admin, solicitud_id))

    @classmethod
    def eliminar_solicitud(cls, solicitud_id):
        with cls.conexion() as conn:
            return conn.execute('DELETE FROM solicitudes WHERE id = ?', (solicitud_id,)).rowcount > 0

    @classmethod
    def autenticar_admin(cls, username, password):
        with cls.conexion() as conn:
            user = conn.execute('SELECT id, username, password_hash, nombre, rol FROM usuarios WHERE username = ?', (username,)).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                return user
            return None

    @classmethod
    def existe_solicitud_para_sistema(cls, rut, sistema):
        with cls.conexion() as conn:
            filas = conn.execute('SELECT * FROM solicitudes WHERE LOWER(TRIM(sistema)) = ? ORDER BY fecha_creacion DESC, id DESC',
                                 (sistema.strip().lower(),)).fetchall()
            return next((fila for fila in filas if limpiar_rut(fila['rut']) == limpiar_rut(rut)), None)

    @classmethod
    def obtener_por_rut(cls, rut):
        return [fila for fila in cls.obtener_todas() if limpiar_rut(fila['rut']) == limpiar_rut(rut)]

    @classmethod
    def actualizar_desde_reporte(cls, rut, sistema, fecha_movimiento, admin_nombre='Sincronización Reporte'):
        """Compatibilidad con el método antiguo. La nueva sincronización no lo usa."""
        with cls.conexion() as conn:
            filas = conn.execute("SELECT id, rut FROM solicitudes WHERE LOWER(TRIM(sistema)) = ? AND estado = 'Pendiente'",
                                 (sistema.strip().lower(),)).fetchall()
            total = 0
            for fila in filas:
                if limpiar_rut(fila['rut']) == limpiar_rut(rut):
                    conn.execute('''UPDATE solicitudes SET estado = 'Gestionada', gestionado_por_admin = ?,
                        fecha_gestion = COALESCE(?, CURRENT_TIMESTAMP) WHERE id = ?''',
                        (admin_nombre, fecha_movimiento, fila['id']))
                    total += 1
            return total
