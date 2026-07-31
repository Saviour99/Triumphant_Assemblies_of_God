from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, PasswordField, TextAreaField, DecimalField,
    DateField, BooleanField, SelectField, HiddenField
)
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, NumberRange, ValidationError

from app.utils import is_youtube_url


def youtube_url_validator(form, field):
    """Only allow youtube.com/youtu.be URLs — this value is embedded
    directly in an <iframe src> on the public site."""
    if field.data and not is_youtube_url(field.data):
        raise ValidationError('Must be a valid YouTube URL (youtube.com or youtu.be).')


class AdminLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])


class AdminForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])


class AdminResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match')]
    )


class AdminProfileForm(FlaskForm):
    avatar = FileField('Profile Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only (jpg, png, gif).')
    ])
    new_password = PasswordField(
        'New Password', validators=[Optional(), Length(min=8)],
        description='Leave blank to keep your current password.'
    )
    confirm_password = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('new_password', message='Passwords must match')]
    )


class AdminAccountManageForm(FlaskForm):
    """Developer-only: edit any admin/developer account (including
    resetting its password), not just your own."""
    username = StringField('Username', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    avatar = FileField('Profile Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only (jpg, png, gif).')
    ])
    new_password = PasswordField(
        'New Password', validators=[Optional(), Length(min=8)],
        description='Leave blank to keep the current password.'
    )
    confirm_password = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('new_password', message='Passwords must match')]
    )


class MemberRegisterForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=255)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match')]
    )


class MemberLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])


class MemberForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])


class MemberResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match')]
    )


class MemberAvatarForm(FlaskForm):
    avatar = FileField('Profile Photo', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only (jpg, png, gif).')
    ])


class AdminMemberForm(FlaskForm):
    """Used by the admin dashboard to add/edit a member."""
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=255)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    password = PasswordField(
        'Password',
        validators=[Optional(), Length(min=8)],
        description='Leave blank to keep the existing password when editing.'
    )
    is_active_member = BooleanField('Active', default=True)


class VideoSermonForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=255)])
    preacher = StringField('Preacher / Writer', validators=[DataRequired(), Length(max=255)])
    youtube_url = StringField('YouTube URL', validators=[DataRequired(), Length(max=500), youtube_url_validator])
    sermon_date = DateField('Date', validators=[DataRequired()])
    message = TextAreaField('Short Message', validators=[Optional()])


class AudioSermonForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=255)])
    preacher = StringField('Preacher / Writer', validators=[DataRequired(), Length(max=255)])
    sermon_date = DateField('Date', validators=[DataRequired()])
    message = TextAreaField('Short Message', validators=[Optional()])
    audio_file = FileField('Audio File', validators=[
        FileRequired(message='Please choose an audio file.'),
        FileAllowed(['mp3', 'mp4'], 'Audio files only (mp3).')
    ])


class AudioSermonEditForm(FlaskForm):
    """Same as AudioSermonForm, but the audio file is optional — leave it
    blank to keep the existing upload and only change the other fields."""
    title = StringField('Title', validators=[DataRequired(), Length(max=255)])
    preacher = StringField('Preacher / Writer', validators=[DataRequired(), Length(max=255)])
    sermon_date = DateField('Date', validators=[DataRequired()])
    message = TextAreaField('Short Message', validators=[Optional()])
    audio_file = FileField('Replace Audio File', validators=[
        Optional(),
        FileAllowed(['mp3', 'mp4'], 'Audio files only (mp3).')
    ])


class DevotionForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=255)])
    quote = StringField('Quote', validators=[DataRequired(), Length(max=500)])
    quote_theme = StringField('Theme', validators=[DataRequired(), Length(max=500)])
    writer_name = StringField("Writer's Name", validators=[DataRequired(), Length(max=255)])
    reflection = TextAreaField('Reflection', validators=[DataRequired()])
    prayer_points = TextAreaField(
        'Prayer Points', validators=[Optional()],
        description='One prayer point per line — each line becomes a bullet.'
    )
    declaration = TextAreaField('Declaration', validators=[DataRequired()])


class LiveStreamForm(FlaskForm):
    is_live = BooleanField('Go Live')
    youtube_url = StringField('YouTube Live URL', validators=[Optional(), Length(max=500), youtube_url_validator])


class EbookForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=255)])
    author = StringField('Author', validators=[DataRequired(), Length(max=255)])
    category = SelectField('Category', choices=[('worship', 'Worship'), ('leadership', 'Leadership')],
                            validators=[DataRequired()])
    summary = TextAreaField('Summary', validators=[Optional()])
    file = FileField(
        'PDF File', validators=[Optional(), FileAllowed(['pdf'], 'PDF files only.')],
        description='Only upload a file you have the rights to distribute. Leave blank to keep listing this title without a download.'
    )


class GivingInitForm(FlaskForm):
    """CSRF-protected JSON-friendly form used by /api/giving/init."""
    amount = DecimalField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    giving_type = SelectField('Giving Type', choices=[
        ('tithe', 'Tithe'), ('offering', 'Offering'), ('missions', 'Missions'),
        ('building_fund', 'Building Fund'), ('other', 'Other')
    ], validators=[DataRequired()])
    donor_name = StringField('Full Name', validators=[DataRequired(), Length(max=255)])
    donor_email = StringField('Email', validators=[DataRequired(), Email()])
