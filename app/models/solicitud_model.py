import sqlite3
import re
from werkzeug.security import generate_password_hash, check_password_hash
from app.config import Config

def limpiar_rut(rut_texto):
    """Elimina puntos, guiones y espacios, dejando solo números y dígito verificador en mayúscula."""
    if not rut_texto:
        return ""
    return re.sub(r'[^0-9kK]', '', str(rut_texto)).upper()

class SolicitudModel:
    @staticmethod
    def get_connection():
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def init_db(cls):
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de solicitudes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS solicitudes (
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
                    fecha_gestion TIMESTAMP DEFAULT NULL
                )
            ''')
            
            # Tabla de usuarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    rol TEXT NOT NULL DEFAULT 'admin'
                )
            ''')
            
            # Crear administrador inicial si no existe
            cursor.execute("SELECT id FROM usuarios WHERE username = 'admin'")
            if not cursor.fetchone():
                admin_hash = generate_password_hash("Admin2026!")
                cursor.execute(
                    "INSERT INTO usuarios (username, password_hash, nombre, rol) VALUES (?, ?, ?, ?)",
                    ('admin', admin_hash, 'Administrador del Sistema', 'admin')
                )
            
            # Migraciones dinámicas de columnas
            cursor.execute("PRAGMA table_info(solicitudes)")
            columnas = [col[1] for col in cursor.fetchall()]
            if 'sistema' not in columnas:
                cursor.execute("ALTER TABLE solicitudes ADD COLUMN sistema TEXT NOT NULL DEFAULT 'Rayen'")
            if 'estado' not in columnas:
                cursor.execute("ALTER TABLE solicitudes ADD COLUMN estado TEXT DEFAULT 'Pendiente'")
            if 'gestionado_por_admin' not in columnas:
                cursor.execute("ALTER TABLE solicitudes ADD COLUMN gestionado_por_admin TEXT DEFAULT NULL")
            if 'fecha_gestion' not in columnas:
                cursor.execute("ALTER TABLE solicitudes ADD COLUMN fecha_gestion TIMESTAMP DEFAULT NULL")
            
            conn.commit()

    @classmethod
    def crear_solicitud(cls, tipo_solicitud, sistema, nombre_completo, rut, correo, centros, gestionado_por, ip_origen):
        query = '''
            INSERT INTO solicitudes (tipo_solicitud, sistema, nombre_completo, rut, correo, centros, gestionado_por, ip_origen, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
        '''
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (tipo_solicitud, sistema, nombre_completo, rut, correo, centros, gestionado_por, ip_origen))
            conn.commit()
            return cursor.lastrowid

    @classmethod
    def obtener_todas(cls):
        query = '''
            SELECT id, tipo_solicitud, sistema, rut, nombre_completo, correo, centros, 
                   gestionado_por, ip_origen, estado, gestionado_por_admin, fecha_creacion, fecha_gestion
            FROM solicitudes
            ORDER BY fecha_creacion DESC
        '''
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()

    @classmethod
    def marcar_como_gestionada(cls, solicitud_id, nombre_admin):
        query = '''
            UPDATE solicitudes
            SET estado = 'Gestionada',
                gestionado_por_admin = ?,
                fecha_gestion = CURRENT_TIMESTAMP
            WHERE id = ?
        '''
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (nombre_admin, solicitud_id))
            conn.commit()

    @classmethod
    def eliminar_solicitud(cls, solicitud_id):
        query = 'DELETE FROM solicitudes WHERE id = ?'
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (solicitud_id,))
            conn.commit()
            return cursor.rowcount > 0

    @classmethod
    def autenticar_admin(cls, username, password):
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password_hash, nombre, rol FROM usuarios WHERE username = ?", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password_hash'], password):
                return user
            return None

    @classmethod
    def existe_solicitud_para_sistema(cls, rut, sistema):
        """Busca si el RUT ya tiene una solicitud previa para el sistema (Rayen o Iris)."""
        rut_limpio = limpiar_rut(rut)
        sistema_limpio = sistema.strip().lower()

        with cls.get_connection() as conn:
            cursor = conn.cursor()
            # Trae nombre_completo para evitar el KeyError/IndexError
            cursor.execute('''
                SELECT id, rut, nombre_completo, sistema, estado, gestionado_por_admin, fecha_gestion, fecha_creacion 
                FROM solicitudes 
                WHERE LOWER(sistema) = ?
            ''', (sistema_limpio,))
            
            registros = cursor.fetchall()
            for r in registros:
                if limpiar_rut(r['rut']) == rut_limpio:
                    return r
            return None

    @classmethod
    def obtener_por_rut(cls, rut):
        """Retorna el historial de solicitudes asociadas a un RUT."""
        rut_limpio = limpiar_rut(rut)
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tipo_solicitud, sistema, rut, nombre_completo, centros, 
                       estado, gestionado_por_admin, fecha_creacion, fecha_gestion
                FROM solicitudes
                ORDER BY fecha_creacion DESC
            ''')
            registros = cursor.fetchall()
            return [r for r in registros if limpiar_rut(r['rut']) == rut_limpio]


    @classmethod
    def actualizar_desde_reporte(cls, rut, sistema, fecha_movimiento, admin_nombre="Sincronización Reporte"):
        """Actualiza el estado a 'Gestionada' si coincide el RUT y el sistema."""
        rut_clean = limpiar_rut(rut)
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            # Buscar solicitudes pendientes para ese RUT y sistema
            cursor.execute('''
                SELECT id, rut FROM solicitudes 
                WHERE LOWER(sistema) = LOWER(?) AND estado = 'Pendiente'
            ''', (sistema.strip(),))
            registros = cursor.fetchall()

            actualizados = 0
            for r in registros:
                if limpiar_rut(r['rut']) == rut_clean:
                    cursor.execute('''
                        UPDATE solicitudes 
                        SET estado = 'Gestionada',
                            gestionado_por_admin = ?,
                            fecha_gestion = COALESCE(?, CURRENT_TIMESTAMP)
                        WHERE id = ?
                    ''', (admin_nombre, fecha_movimiento, r['id']))
                    actualizados += 1
            
            conn.commit()
            return actualizados