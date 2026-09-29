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
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    @classmethod
    def crear_solicitud(cls, tipo_solicitud, nombre_completo, rut, correo, centros, gestionado_por, ip_origen):
        query = '''
            INSERT INTO solicitudes (tipo_solicitud, nombre_completo, rut, correo, centros, gestionado_por, ip_origen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (tipo_solicitud, nombre_completo, rut, correo, centros, gestionado_por, ip_origen))
            conn.commit()
            return cursor.lastrowid

    @classmethod
    def obtener_todas(cls):
        query = '''
            SELECT id, tipo_solicitud, rut, nombre_completo, correo, centros, gestionado_por, fecha_creacion, ip_origen
            FROM solicitudes
            ORDER BY fecha_creacion DESC
        '''
        with cls.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()