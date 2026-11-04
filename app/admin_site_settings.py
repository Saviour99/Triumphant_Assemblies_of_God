"""
Admin: Site settings — the church's public contact details, service times,
social links and other general information shown across the public site.

Only the developer and pastor roles may open this page (an 'admin' account
gets 403 even with every section permission). Routes register on `admin_bp`;
imported at the bottom of app/admin.py. Storage/caching lives in
app/site_settings.py.
"""

import re

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import Form, StringField, TextAreaField, SelectField, FieldList, FormField
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp, ValidationError

from app.admin import admin_bp
from app.decorators import roles_required
from app.models import SiteSettingsLog
from app import site_settings as ss

SETTINGS_ROLES = ('developer', 'pastor')

_TAG_RE = re.compile(r'<[^>]*>')
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def _clean(value, multiline=False):
    """Trim, drop HTML tags and control characters. (Not app.utils.sanitize_text:
    that strips & + ( ) ' which real phone numbers, URLs and text need.
    Output is autoescaped on render regardless.)"""
    if value is None:
        return ''
    value = _CTRL_RE.sub('', _TAG_RE.sub('', str(value)))
    if multiline:
        lines = [ln.strip() for ln in value.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
        return '\n'.join(lines).strip()
    return ' '.join(value.split())


def _phone_check(form, field):
    if field.data and not ss.normalize_phone(field.data):
        raise ValidationError('Enter a phone number like 050 111 6130 or +233 50 111 6130.')


def _social_check(key):
    def check(form, field):
        if field.data:
            err = ss.social_url_error(key, field.data.strip())
            if err:
                raise ValidationError(err)
    return check


_TIME = Regexp(ss.TIME_RE, message='Use 24-hour time, HH:MM (e.g. 07:00 or 19:00).')


class ServiceTimeForm(Form):
    day = SelectField('Day', choices=[(d, d) for d in ss.DAYS])
    name = StringField('Service', validators=[DataRequired(message='Name the service.'),
                                              Length(max=ss.SERVICE_NAME_MAX)])
    start = StringField('Starts', validators=[DataRequired(message='Enter a start time.'), _TIME])
    end = StringField('Ends', validators=[Optional(), _TIME])
    note = StringField('Note', validators=[Optional(), Length(max=ss.SERVICE_NOTE_MAX)])

    def validate_end(self, field):
        if field.data and self.start.data and ss.TIME_RE.match(self.start.data) \
                and field.data <= self.start.data:
            raise ValidationError('The end time must be after the start time.')


def _len(key):
    return Length(max=ss.MAX_LENGTHS[key])


class SiteSettingsForm(FlaskForm):
    name = StringField('Church name', validators=[DataRequired(), _len('name')])
    tagline = StringField('Tagline', validators=[Optional(), _len('tagline')])
    footer_about = TextAreaField('Footer about text', validators=[Optional(), _len('footer_about')])

    address = StringField('Address', validators=[DataRequired(), _len('address')])
    digital_address = StringField('Digital address (GhanaPost GPS)',
                                  validators=[Optional(), _len('digital_address')])
    maps_query = StringField('Google Maps search text', validators=[DataRequired(), _len('maps_query')])

    phone = StringField('Phone', validators=[DataRequired(), _len('phone'), _phone_check])
    phone_alt = StringField('Second phone', validators=[Optional(), _len('phone_alt'), _phone_check])
    whatsapp = StringField('WhatsApp number', validators=[Optional(), _len('whatsapp'), _phone_check])
    email = StringField('Email', validators=[DataRequired(), Email(), _len('email')])
    office_hours = TextAreaField('Office hours', validators=[Optional(), _len('office_hours')])

    service_times = FieldList(FormField(ServiceTimeForm), min_entries=0,
                              max_entries=ss.MAX_SERVICE_ROWS)

    giving_note = TextAreaField('Bank / Mobile Money details', validators=[Optional(), _len('giving_note')])

    social_facebook = StringField('Facebook', validators=[Optional(), _len('social_facebook'), _social_check('facebook')])
    social_instagram = StringField('Instagram', validators=[Optional(), _len('social_instagram'), _social_check('instagram')])
    social_youtube = StringField('YouTube', validators=[Optional(), _len('social_youtube'), _social_check('youtube')])
    social_tiktok = StringField('TikTok', validators=[Optional(), _len('social_tiktok'), _social_check('tiktok')])
    social_x = StringField('X (Twitter)', validators=[Optional(), _len('social_x'), _social_check('x')])
    social_whatsapp_channel = StringField('WhatsApp channel', validators=[Optional(), _len('social_whatsapp_channel'),
                                                                          _social_check('whatsapp_channel')])


_MULTILINE = {'office_hours', 'giving_note', 'footer_about'}


def _form_values(form):
    values = {}
    for key in ss.SETTING_KEYS:
        if key == 'service_times':
            rows = [{
                'day': e.form.day.data,
                'name': _clean(e.form.name.data),
                'start': (e.form.start.data or '').strip(),
                'end': (e.form.end.data or '').strip(),
                'note': _clean(e.form.note.data),
            } for e in form.service_times.entries]
            values[key] = ss.clean_service_times(rows)
        else:
            values[key] = _clean(getattr(form, key).data, multiline=key in _MULTILINE)
    return values


@admin_bp.route('/site-settings', methods=['GET', 'POST'])
@roles_required(*SETTINGS_ROLES)
def site_settings():
    current = ss.load_raw_settings()
    if request.method == 'POST':
        form = SiteSettingsForm()
    else:
        form = SiteSettingsForm(data=current)

    if form.validate_on_submit():
        changed = ss.save_settings(_form_values(form), current_user)
        if changed:
            flash(f'Site information saved ({len(changed)} field{"s" if len(changed) != 1 else ""} '
                  'updated). The public site shows the new details now.', 'success')
        else:
            flash('No changes to save.', 'info')
        return redirect(url_for('admin.site_settings'))
    if request.method == 'POST':
        flash('Please fix the highlighted fields.', 'danger')

    logs = SiteSettingsLog.query.order_by(SiteSettingsLog.changed_at.desc(),
                                          SiteSettingsLog.id.desc()).limit(20).all()
    return render_template('admin/site_settings.html', form=form, logs=logs,
                           days=ss.DAYS, max_rows=ss.MAX_SERVICE_ROWS)
