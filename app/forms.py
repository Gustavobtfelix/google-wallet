from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, EmailField, PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

DT_FORMAT = "%Y-%m-%dT%H:%M"


class LoginForm(FlaskForm):
    email = EmailField("E-mail", validators=[DataRequired(), Email()])
    password = PasswordField("Senha", validators=[DataRequired()])
    submit = SubmitField("Entrar")


class VisitorPassForm(FlaskForm):
    visitor_name = StringField("Nome do visitante", validators=[DataRequired(), Length(max=120)])
    visitor_email = EmailField("E-mail do visitante", validators=[DataRequired(), Email(), Length(max=255)])
    visitor_document = StringField("Documento (RG/CPF)", validators=[Optional(), Length(max=30)])
    company = StringField("Empresa do visitante", validators=[Optional(), Length(max=120)])
    host_name = StringField("Anfitrião", validators=[DataRequired(), Length(max=120)])
    host_email = EmailField("E-mail do anfitrião", validators=[Optional(), Email(), Length(max=255)])
    visit_start = DateTimeLocalField("Entrada", format=DT_FORMAT, validators=[DataRequired()])
    visit_end = DateTimeLocalField("Saída", format=DT_FORMAT, validators=[DataRequired()])
    purpose = TextAreaField("Motivo da visita", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Salvar")

    def validate_visit_end(self, field):
        if self.visit_start.data and field.data and field.data <= self.visit_start.data:
            raise ValidationError("A saída deve ser posterior à entrada.")
