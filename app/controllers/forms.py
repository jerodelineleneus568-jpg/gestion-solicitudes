import re
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Email, Length, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput

def validar_rut(form, field):
    rut_limpio = field.data.replace(".", "").replace("-", "").strip().upper()
    if not re.match(r'^[0-9]+[0-9K]$', rut_limpio) or len(rut_limpio) < 8:
        raise ValidationError('Formato de RUT no válido (ejemplo: 12345678-9).')
    
    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]
    
    suma = 0
    multiplicador = 2
    for c in reversed(cuerpo):
        suma += int(c) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
    
    resto = suma % 11
    dv_esperado = 11 - resto
    if dv_esperado == 11:
        dv_calculado = '0'
    elif dv_esperado == 10:
        dv_calculado = 'K'
    else:
        dv_calculado = str(dv_esperado)
        
    if dv != dv_calculado:
        raise ValidationError('El RUT ingresado no es válido (dígito verificador incorrecto).')

class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()

# Lista extensa de centros institucionales
LISTA_CENTROS = [
    ('EDIFICIO_CONSISTORIAL', 'Edificio Consistorial (Central)'),
    ('DEPTO_INFORMATICA', 'Departamento de Informática'),
    ('DIRECCION_OBRAS', 'Dirección de Obras Municipales (DOM)'),
    ('TRANSITO', 'Dirección de Tránsito y Transporte'),
    ('DIDECO_CENTRAL', 'DIDECO - Casa Central'),
    ('DIDECO_NORTE', 'DIDECO - Sede Norte'),
    ('DIDECO_SUR', 'DIDECO - Sede Sur'),
    ('SALUD_CESFAM_1', 'CESFAM Dr. Amador Neghme'),
    ('SALUD_CESFAM_2', 'CESFAM Edgardo Enríquez'),
    ('SALUD_CECOSF_1', 'CECOSF Villa Sur'),
    ('SALUD_CECOSF_2', 'CECOSF San Joaquín'),
    ('SALUD_FARMACIA', 'Farmacia Popular Comunal'),
    ('SEGURIDAD_COMUNAL', 'Dirección de Seguridad y Vigilancia'),
    ('OPERACIONES_TALLERES', 'Dirección de Operaciones y Talleres'),
    ('ASEO_OR NATO', 'Departamento de Aseo y Ornato'),
    ('MEDIO_AMBIENTE', 'Dirección de Medio Ambiente'),
    ('ADMINISTRACION_FINANZAS', 'Dirección de Administración y Finanzas (DAF)'),
    ('JUZGADO_POLICIA_LOCAL', 'Juzgado de Policía Local'),
    ('BIBLIOTECA_COMUNAL', 'Biblioteca Pública Comunal'),
    ('CORPORACION_DEPORTES', 'Centro Deportivo / Estadio Comunal'),
    ('CENTRO_CULTURAL', 'Centro Cultural Comunal')
]

class FormularioSolicitud(FlaskForm):
    tipo_solicitud = SelectField(
        'Tipo de Solicitud',
        choices=[
            ('Creación de cuenta', 'Creación de cuenta'),
            ('Reactivación de cuenta', 'Reactivación de cuenta')
        ],
        validators=[DataRequired(message="Debe seleccionar un tipo de solicitud.")]
    )
    
    nombre_completo = StringField(
        'Nombre Completo',
        validators=[
            DataRequired(message="El nombre completo es obligatorio."),
            Length(min=3, max=100, message="El nombre debe tener entre 3 y 100 caracteres.")
        ]
    )
    
    rut = StringField(
        'RUT',
        validators=[
            DataRequired(message="El RUT es obligatorio."),
            Length(min=3, max=20, message="El RUT debe tener entre 3 y 20 caracteres.")
        ]
    )
    
    # Se eliminó la palabra "Institucional"
    correo = StringField(
        'Correo',
        validators=[
            DataRequired(message="El correo es obligatorio."),
            Email(message="Ingrese un correo electrónico válido.")
        ]
    )
    
    centros = SelectMultipleField(
        'Centro(s) al que pertenece',
        choices=[
            ('Centro Médico Central', 'Centro Médico Central'),
            ('Centro Norte', 'Centro Norte'),
            ('Centro Sur', 'Centro Sur'),
            ('Centro Oriente', 'Centro Oriente'),
            ('Centro Poniente', 'Centro Poniente')
        ],
        validators=[DataRequired(message="Debe seleccionar al menos un centro.")]
    )
    
    submit = SubmitField('Enviar Solicitud')