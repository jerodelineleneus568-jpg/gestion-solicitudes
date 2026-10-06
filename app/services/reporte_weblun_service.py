"""Consulta por RUT del Excel original; no depende de Flask ni de una sesión."""
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd


def normalizar(valor):
    texto = unicodedata.normalize('NFKD', str(valor).strip().lower())
    return ' '.join(''.join(c for c in texto if not unicodedata.combining(c)).split()).rstrip('.')


def rut_normalizado(valor):
    return re.sub(r'[^0-9kK]', '', str(valor)).upper()


def fecha_normalizada(valor):
    """Fechas chilenas: día/mes/año. Un vacío permanece vacío."""
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        fecha = pd.to_datetime(texto, format='mixed', dayfirst=True, errors='raise')
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Hay una fecha no reconocida en Último login o Último movimiento.') from None
    if pd.isna(fecha):
        return None
    return fecha.to_pydatetime()


def leer_indice_reporte(ruta):
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError('No está disponible el Excel asociado a la sincronización.')
    tabla = pd.read_excel(ruta, header=None, dtype=str, keep_default_na=False)
    cabecera = None
    for numero, fila in tabla.head(30).iterrows():
        nombres = [normalizar(v) for v in fila]
        if ('run' in nombres or 'rut' in nombres) and 'ultimo login' in nombres:
            cabecera = numero
            break
    if cabecera is None:
        raise ValueError('El Excel debe contener RUN/RUT y Último login.')
    nombres = [normalizar(v) for v in tabla.loc[cabecera]]
    no_vacios = [n for n in nombres if n]
    if len(set(no_vacios)) != len(no_vacios):
        raise ValueError('El Excel contiene encabezados repetidos.')
    posiciones = {n: i for i, n in enumerate(nombres) if n}
    rut_pos = posiciones.get('run', posiciones.get('rut'))
    login_pos = posiciones['ultimo login']
    movimiento_pos = posiciones.get('ultimo mov', posiciones.get('ultimo movimiento'))
    if movimiento_pos is None:
        raise ValueError('El Excel debe contener Último mov. o Último movimiento.')
    aplicacion_pos = posiciones.get('aplicacion')
    indice = {}
    for _, fila in tabla.loc[cabecera + 1:].iterrows():
        rut = rut_normalizado(fila.iloc[rut_pos])
        if not rut:
            continue
        if aplicacion_pos is not None and normalizar(fila.iloc[aplicacion_pos]) != 'rayen':
            continue
        datos = indice.setdefault(rut, {'ultimo_login': None, 'ultimo_movimiento': None})
        for clave, posicion in [('ultimo_login', login_pos), ('ultimo_movimiento', movimiento_pos)]:
            fecha = fecha_normalizada(fila.iloc[posicion])
            if fecha is not None and (datos[clave] is None or fecha > datos[clave]):
                datos[clave] = fecha
    return indice


def datos_para_solicitud(rut, sistema, indice):
    if str(sistema).strip().lower() != 'rayen':
        return None, None, 'No corresponde (Iris)'
    if indice is None:
        return None, None, 'Sin reporte disponible'
    datos = indice.get(rut_normalizado(rut))
    if datos is None:
        return None, None, 'No encontrado en el reporte'
    def serializar(fecha):
        return fecha.isoformat(sep=' ', timespec='seconds') if fecha else None
    return serializar(datos['ultimo_login']), serializar(datos['ultimo_movimiento']), 'Existe en el reporte'
