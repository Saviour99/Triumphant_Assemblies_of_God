"""
Admin: Integrations (email provider credentials) — DEVELOPER ONLY.

/admin/integrations lets the developer enter the Resend API key, audience
ID and mail addresses in the dashboard instead of .env. Storage, encryption
and the read API live in app/integrations.py (`get_integration`). Routes
register on `admin_bp`; imported at the bottom of app/admin.py.

Security: secret values are never rendered back (masked only), never
logged, never put in flash/error messages; every POST is CSRF-protected and
rate-limited; responses carry Cache-Control: no-store.
"""

import logging

from flask import render_template, redirect, url_for, flash, make_response
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, HiddenField
from wtforms.validators import Optional, Length, ValidationError

from app import db, limiter
from app.admin import admin_bp
from app.decorators import developer_required
from app.models import IntegrationSettingLog
from app import integrations as integ

log = logging.getLogger(__name__)

POST_LIMIT = '20 per minute;100 per hour'
TEST_LIMIT = '5 per minute;30 per hour'

# Form field name -> integration key (all non-secret except the API key).
TEXT_FIELDS = {
    'audience_id': 'RESEND_AUDIENCE_ID',
    'mail_from': 'MAIL_FROM',
    'mail_reply_to': 'MAIL_REPLY_TO',
    'mail_notify_to': 'MAIL_NOTIFY_TO',
}


def _addr_check(allow_name):
    def check(form, field):
        if field.data and field.data.strip() and not integ.valid_address(field.data, allow_name):
            raise ValidationError('Use "Name <email@domain>" or a plain email address.'
                                  if allow_name else 'Enter a valid email address.')
    return check


class IntegrationsForm(FlaskForm):
    api_key = PasswordField('Resend API key', validators=[Optional(), Length(max=200)])
    audience_id = StringField('Audience ID', validators=[Optional(), Length(max=100)])
    mail_from = StringField('From address', validators=[Optional(), Length(max=200), _addr_check(True)])
    mail_reply_to = StringField('Reply-to address', validators=[Optional(), Length(max=200), _addr_check(True)])
    mail_notify_to = StringField('Notification inbox', validators=[Optional(), Length(max=200), _addr_check(False)])

    def validate_api_key(self, field):
        val = (field.data or '').strip()
        if val and (not val.startswith('re_') or any(c.isspace() for c in val)):
            raise ValidationError('That doesn\'t look like a Resend API key (they start with "re_").')


class RemoveForm(FlaskForm):
    key = HiddenField()


class TestEmailForm(FlaskForm):
    pass


def _audit(key, action):
    db.session.add(IntegrationSettingLog(setting_key=key, action=action, admin_id=current_user.id))


def _resend_client():
    try:
        from app import resend_client
        return resend_client
    except Exception:
        return None


def _no_store(resp):
    resp = make_response(resp)
    resp.headers['Cache-Control'] = 'no-store, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


def _render(form):
    statuses = {k: integ.integration_status(k) for k in integ.INTEGRATION_KEYS}
    try:
        recent = (IntegrationSettingLog.query
                  .order_by(IntegrationSettingLog.changed_at.desc()).limit(20).all())
    except Exception:
        db.session.rollback()
        recent = []
    rc = _resend_client()
    return _no_store(render_template(
        'admin/integrations.html', form=form, statuses=statuses,
        meta=integ.INTEGRATION_KEYS, text_fields=TEXT_FIELDS,
        remove_form=RemoveForm(), test_form=TestEmailForm(),
        test_available=rc is not None and hasattr(rc, 'send_email'),
        recent=recent,
    ))


@admin_bp.route('/integrations', methods=['GET', 'POST'])
@developer_required
@limiter.limit(POST_LIMIT, methods=['POST'])
def integrations():
    form = IntegrationsForm()
    if form.is_submitted():
        if not form.validate():
            return _render(form)
        changed = []
        api_key = (form.api_key.data or '').strip()
        if api_key:  # blank keeps the current value
            integ.set_integration('RESEND_API_KEY', api_key, current_user.id)
            changed.append('RESEND_API_KEY')
        for fname, key in TEXT_FIELDS.items():
            new = (getattr(form, fname).data or '').strip()
            status = integ.integration_status(key)
            current_saved = integ.get_integration(key) if status['source'] == 'admin' else None
            if new and new != current_saved:
                integ.set_integration(key, new, current_user.id)
                changed.append(key)
            elif not new and status['source'] == 'admin':
                # Field cleared -> drop the saved value, fall back to .env.
                integ.remove_integration(key)
                changed.append(key)
        for key in changed:
            _audit(key, 'saved')
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception('Saving integration settings failed')
            flash('Could not save settings. Has init_db.py been run?', 'danger')
            return redirect(url_for('admin.integrations'))
        integ.invalidate_cache()
        log.info('Integration settings saved by admin %s: %s', current_user.id, ', '.join(changed) or 'none')
        flash(f'Saved {len(changed)} setting(s).' if changed else 'No changes.', 'success' if changed else 'info')
        return redirect(url_for('admin.integrations'))

    # Prefill non-secret fields with the admin-saved value only (not .env).
    for fname, key in TEXT_FIELDS.items():
        if integ.integration_status(key)['source'] == 'admin':
            getattr(form, fname).data = integ.get_integration(key)
    return _render(form)


@admin_bp.route('/integrations/remove', methods=['POST'])
@developer_required
@limiter.limit(POST_LIMIT)
def integration_remove():
    form = RemoveForm()
    key = form.key.data if form.validate_on_submit() else None
    if key not in integ.INTEGRATION_KEYS:
        flash('Unknown setting.', 'danger')
        return redirect(url_for('admin.integrations'))
    if integ.remove_integration(key):
        _audit(key, 'removed')
        db.session.commit()
        integ.invalidate_cache()
        log.info('Integration setting %s removed by admin %s', key, current_user.id)
        flash(f'Removed the saved {integ.INTEGRATION_KEYS[key]["label"]}.', 'success')
    else:
        flash('Nothing saved to remove.', 'info')
    return redirect(url_for('admin.integrations'))


@admin_bp.route('/integrations/test', methods=['POST'])
@developer_required
@limiter.limit(TEST_LIMIT)
def integration_test():
    form = TestEmailForm()
    if not form.validate_on_submit():
        flash('Session expired, please try again.', 'danger')
        return redirect(url_for('admin.integrations'))
    rc = _resend_client()
    if rc is None or not hasattr(rc, 'send_email'):
        flash('Test not available: the Resend client is not installed yet.', 'warning')
        return redirect(url_for('admin.integrations'))

    api_key = integ.get_integration('RESEND_API_KEY')
    sender = integ.get_integration('MAIL_FROM')
    if not api_key:
        result = {'ok': False, 'message': 'No Resend API key is set.'}
    elif not sender:
        result = {'ok': False, 'message': 'Set a From address first.'}
    elif not current_user.email:
        result = {'ok': False, 'message': 'Your account has no email address.'}
    else:
        try:
            email_id = rc.send_email(
                sender, current_user.email, 'Test email from the church website',
                html='<p>This is a test from <strong>Admin → Integrations</strong>. '
                     'Resend is configured correctly.</p>',
                text='This is a test from Admin > Integrations. Resend is configured correctly.',
                reply_to=integ.get_integration('MAIL_REPLY_TO'),
            )
            result = {'ok': True, 'message': f'Sent to {current_user.email}'
                      + (f' (Resend id {email_id}).' if email_id else '.')}
        except Exception as exc:
            msg = getattr(exc, 'message', '') or type(exc).__name__
            if api_key:
                msg = msg.replace(api_key, '[redacted]')
            result = {'ok': False, 'message': f'Send failed: {msg[:300]}'}
    _audit('RESEND_API_KEY', 'test_sent' if result['ok'] else 'test_failed')
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    flash('Test email: ' + result['message'],
          'success' if result['ok'] else 'danger')
    return redirect(url_for('admin.integrations'))
