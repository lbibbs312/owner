from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired


class DirectMessageForm(FlaskForm):
    receiver_id = SelectField("Send To", coerce=int)
    content = TextAreaField("Message", validators=[DataRequired()])
    submit = SubmitField("Send")


class AnnouncementForm(FlaskForm):
    title = StringField("Announcement Title", validators=[DataRequired()])
    body = TextAreaField("Announcement Body", validators=[DataRequired()])
    submit = SubmitField("Post Announcement")


class KnowledgeBaseForm(FlaskForm):
    title = StringField("Tip Title", validators=[DataRequired()])
    body = TextAreaField("Tip Body", validators=[DataRequired()])
    submit = SubmitField("Add Tip")
