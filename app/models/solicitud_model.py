import sqlite3
from app.config import Config

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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS solicitudes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo_solicitud TEXT NOT NULL,
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
            # Migración automática si la tabla ya existía sin las nuevas columnas
            cursor.execute("PRAGMA table_info(solicitudes)")
            columnas = [col[1] for col in cursor.fetchall()]
            if 'estado' not in columnas:
                cursor.execute("ALTER TABLE solicitudes ADD COLUMN estado TEXT DEFAULT 'Pendiente'")
            if 'gestionado_por_admin' not in columnas:
                cursor.execute("ALTER TABLE solicitudes ADD COLUMN gestionado_por_admin TEXT DEFAULT NULL")
            if 'fecha_gestion' not in columnas:
                cursor.execute("ALTER TABLE solicitudes ADD COLUMN fecha_gestion TIMESTAMP DEFAULT NULL")
            conn.commit()

    @classmethod
    def crear_solicitud(cls, tipo_solicitud, nombre_completo, rut, correo, centros, gestionado_por, ip_origen):
        query = '''
            INSERT INTO solicitudes (tipo_solicitud, nombre_completo, rut, correo, centros, gestionado_por, ip_origen, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente')
        '''
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (tipo_solicitud, nombre_completo, rut, correo, centros, gestionado_por, ip_origen))
            conn.commit()
            return cursor.lastrowid

    @classmethod
    def obtener_todas(cls):
        query = '''
            SELECT id, tipo_solicitud, rut, nombre_completo, correo, centros, 
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