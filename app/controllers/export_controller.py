import io
import pandas as pd
from flask import Blueprint, send_file, abort
from app.models.solicitud_model import SolicitudModel

export_bp = Blueprint('export', __name__)

@export_bp.route('/exportar/excel')
def exportar_excel():
    filas = SolicitudModel.obtener_todas()
    
    if not filas:
        abort(404, description="No hay registros disponibles para exportar.")

    datos = [
        {
            "ID": f["id"],
            "Tipo Solicitud": f["tipo_solicitud"],
            "RUT": f["rut"],
            "Nombre Completo": f["nombre_completo"],
            "Correo": f["correo"],
            "Centros": f["centros"],
            "Gestionado Por": f["gestionado_por"],
            "Fecha Registro": f["fecha_creacion"],
            "IP Origen": f["ip_origen"]
        }
        for f in filas
    ]
    df = pd.DataFrame(datos)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Solicitudes')
        worksheet = writer.sheets['Solicitudes']
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

    output.seek(0)
    return send_file(
        output,
        download_name='Reporte_Consolidado_Solicitudes.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )