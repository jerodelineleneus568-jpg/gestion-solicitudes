"""Recomendaciones de pasivación por RUN, usando únicamente el reporte local."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from app.services.reporte_weblun_service import normalizar, rut_normalizado, fecha_normalizada

ZONA_CHILE = ZoneInfo('America/Santiago')


def fecha_hoy_chile():
    return datetime.now(ZONA_CHILE).date()


def evaluar_pasivacion(ultimo_login, ultimo_movimiento, hoy=None, fecha_invalida=False):
    """Ambas condiciones: >=2 días desde login Y >=7 días desde movimiento."""
    hoy = hoy or fecha_hoy_chile()
    dias_login = (hoy - ultimo_login.date()).days if ultimo_login is not None else None
    dias_movimiento = (hoy - ultimo_movimiento.date()).days if ultimo_movimiento is not None else None
    if fecha_invalida:
        estado, motivo = 'Revisar', 'El reporte contiene una fecha no reconocida para este RUN.'
    elif any(d is not None and d < 0 for d in (dias_login, dias_movimiento)):
        estado, motivo = 'Revisar', 'Hay una fecha posterior al día de evaluación.'
    elif dias_login is None or dias_movimiento is None:
        estado, motivo = 'Revisar', 'Falta último login o último movimiento; no se puede completar la regla.'
    elif dias_login >= 2 and dias_movimiento >= 7:
        estado, motivo = 'Puede pasivarse', 'Cumple ambas condiciones: login hace 2 días o más y movimiento hace 7 días o más.'
    else:
        estado = 'No pasivar'
        if dias_login < 2 and dias_movimiento < 7:
            motivo = 'Tiene login reciente y movimiento reciente.'
        elif dias_login < 2:
            motivo = 'El último login fue hace menos de 2 días.'
        else:
            motivo = 'El último movimiento fue hace menos de 7 días.'
    return {'dias_login': dias_login, 'dias_movimiento': dias_movimiento,
            'recomendacion': estado, 'motivo': motivo}


def calcular_reporte_pasivacion(ruta_excel, hoy=None):
    hoy = hoy or fecha_hoy_chile()
    ruta = Path(ruta_excel)
    if not ruta.is_file():
        raise ValueError('No se encuentra el Excel sincronizado. Realiza una nueva extracción de WebLun.')
    tabla = pd.read_excel(ruta, header=None, dtype=str, keep_default_na=False)
    cabecera = None
    for numero, fila in tabla.head(30).iterrows():
        nombres = [normalizar(v) for v in fila]
        if ('run' in nombres or 'rut' in nombres) and 'ultimo login' in nombres:
            cabecera = numero
            break
    if cabecera is None:
        raise ValueError('El reporte no contiene RUN/RUT y Último login.')
    nombres = [normalizar(v) for v in tabla.loc[cabecera]]
    no_vacios = [n for n in nombres if n]
    if len(no_vacios) != len(set(no_vacios)):
        raise ValueError('El reporte contiene encabezados repetidos.')
    columnas = {nombre: pos for pos, nombre in enumerate(nombres) if nombre}
    rut_pos = columnas.get('run', columnas.get('rut'))
    login_pos = columnas['ultimo login']
    movimiento_pos = columnas.get('ultimo mov', columnas.get('ultimo movimiento'))
    if movimiento_pos is None:
        raise ValueError('El reporte no contiene Último mov. o Último movimiento.')
    nombre_pos = columnas.get('nombre funcionario', columnas.get('nombre completo', columnas.get('nombre')))
    centro_pos = columnas.get('establecimiento', columnas.get('centro'))
    estado_pos = columnas.get('estado actual')
    aplicacion_pos = columnas.get('aplicacion')
    por_rut = {}
    for _, fila in tabla.loc[cabecera + 1:].iterrows():
        if aplicacion_pos is not None and normalizar(fila.iloc[aplicacion_pos]) != 'rayen':
            continue
        rut = rut_normalizado(fila.iloc[rut_pos])
        if not rut:
            continue
        datos = por_rut.setdefault(rut, {
            'rut': str(fila.iloc[rut_pos]).strip(), 'nombre': '',
            'centros': set(), 'estados': set(), 'ultimo_login': None,
            'ultimo_movimiento': None, 'fecha_invalida': False,
        })
        if nombre_pos is not None and not datos['nombre']:
            datos['nombre'] = str(fila.iloc[nombre_pos]).strip()
        if centro_pos is not None:
            centro = str(fila.iloc[centro_pos]).strip()
            if centro:
                datos['centros'].add(centro)
        if estado_pos is not None:
            estado = str(fila.iloc[estado_pos]).strip()
            if estado:
                datos['estados'].add(estado)
        for clave, posicion in [('ultimo_login', login_pos), ('ultimo_movimiento', movimiento_pos)]:
            try:
                fecha = fecha_normalizada(fila.iloc[posicion])
            except ValueError:
                datos['fecha_invalida'] = True
                continue
            if fecha is not None and (datos[clave] is None or fecha > datos[clave]):
                datos[clave] = fecha
    filas = []
    for datos in por_rut.values():
        resultado = evaluar_pasivacion(datos['ultimo_login'], datos['ultimo_movimiento'], hoy, datos['fecha_invalida'])
        estados_normalizados = {normalizar(e) for e in datos['estados']}
        # El original puede incluir cuentas que ya no están activas.
        if resultado['recomendacion'] != 'Revisar' and estado_pos is not None:
            if not estados_normalizados:
                resultado.update(recomendacion='Revisar', motivo='El reporte no informa el estado actual.')
            elif 'activo' not in estados_normalizados:
                resultado.update(recomendacion='No pasivar', motivo='El RUN no tiene un registro Activo en este reporte.')
        filas.append({
            'rut': datos['rut'], 'nombre': datos['nombre'] or 'Sin información',
            'establecimiento': ' / '.join(sorted(datos['centros'])) or 'Sin información',
            'estado_actual': ' / '.join(sorted(datos['estados'])) or 'Sin información',
            'ultimo_login': datos['ultimo_login'].strftime('%d/%m/%Y %H:%M') if datos['ultimo_login'] else 'Sin información',
            'ultimo_movimiento': datos['ultimo_movimiento'].strftime('%d/%m/%Y %H:%M') if datos['ultimo_movimiento'] else 'Sin información',
            **resultado,
        })
    orden = {'Puede pasivarse': 0, 'Revisar': 1, 'No pasivar': 2}
    filas.sort(key=lambda fila: (orden[fila['recomendacion']], fila['nombre'].casefold(), fila['rut']))
    resumen = {estado: sum(f['recomendacion'] == estado for f in filas) for estado in orden}
    resumen['total'] = len(filas)
    return filas, resumen
