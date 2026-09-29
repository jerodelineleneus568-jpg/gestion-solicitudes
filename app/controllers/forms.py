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

class FormularioSolicitud(FlaskForm):
    tipo_solicitud = SelectField(
        'Tipo de Solicitud',
        choices=[('', 'Seleccione...'), ('CREACION', 'Creación de cuenta'), ('REACTIVACION', 'Reactivación de cuenta')],
        validators=[DataRequired(message='Debe seleccionar un tipo de solicitud.')]
    )
    nombre_completo = StringField(
        'Nombre Completo',
        validators=[DataRequired(message='El nombre es obligatorio.'), Length(min=3, max=120)]
    )
    rut = StringField(
        'RUT',
        validators=[DataRequired(message='El RUT es obligatorio.'), validar_rut]
    )
    correo = StringField(
        'Correo Institucional',
        validators=[DataRequired(message='El correo es obligatorio.'), Email(message='Correo electrónico inválido.')]
    )
    centros = MultiCheckboxField(
        'Centro(s) al que pertenece',
        choices=[
            ('CENTRO_NORTE', 'Centro Norte'),
            ('CENTRO_SUR', 'Centro Sur'),
            ('CASA_CENTRAL', 'Casa Central'),
            ('DEPTO_INFORMATICA', 'Departamento de Informática'),
            ('DIRECCION_OBRAS', 'Dirección de Obras')
        ],
        validators=[DataRequired(message='Debe seleccionar al menos un centro.')]
    )
    gestionado_por = StringField(
        'Gestionado Por (Jefatura o Solicitante)',
        validators=[DataRequired(message='Este campo es obligatorio.'), Length(min=3, max=100)]
    )
    submit = SubmitField('Enviar Solicitud')