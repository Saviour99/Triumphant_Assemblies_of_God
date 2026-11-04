"""
Admin newsletter: write a newsletter in plain text, preview it as the
designed HTML email, save drafts, and send it to every subscriber as a
Resend Broadcast (app/newsletter_resend.py, over app/resend_client.py).

Routes live on the existing `admin_bp` (imported once at the bottom of
app/admin.py), so URLs are /admin/newsletter/...; the subscriber list at
/admin/newsletter-subscribers (admin.newsletter_subscribers_list) stays the
section's landing page and links here.

Double-send protection: a campaign's status only moves via a single
conditional UPDATE (`_transition`, same pattern as
app/routes.py::_set_donation_status_once). Sending first flips
draft|failed -> sending; a second click (or a second admin) finds no row in
draft|failed and is turned away before anything reaches Resend. The send
call itself also carries an Idempotency-Key.
"""

from datetime import datetime, timedelta, timezone

from flask import (
    render_template, redirect, url_for, flash, request, current_app, Response, abort
)
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app import db, limiter
from app import newsletter_resend as provider
from app.admin import admin_bp
from app.decorators import admin_required, permission_required
from app.models import NewsletterCampaign, NewsletterSubscriber
from app.newsletter_render import render_email, is_http_url

EDITABLE = ('draft', 'failed')
BODY_MAX = 20000
PROVIDER = 'resend'
STUCK_AFTER = timedelta(minutes=15)


def _utcnow():
    """Naive UTC, matching the DateTime columns elsewhere (models.py's
    default=datetime.utcnow), without the deprecated utcnow() call."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============ FORM ============

def _http_url(form, field):
    if field.data and not is_http_url(field.data):
        raise ValidationError('Use a full web address starting with http:// or https://.')


class NewsletterForm(FlaskForm):
    subject = StringField('Subject', validators=[DataRequired(), Length(max=150)])
    preview_text = StringField('Preview text', validators=[Optional(), Length(max=150)])
    body_text = TextAreaField('Message', validators=[DataRequired(), Length(max=BODY_MAX)])
    cta_label = StringField('Button label', validators=[Optional(), Length(max=40)])
    cta_url = StringField('Button link', validators=[Optional(), Length(max=500), _http_url])

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators)
        label = (self.cta_label.data or '').strip()
        url = (self.cta_url.data or '').strip()
        if label and not url:
            self.cta_url.errors.append('Add the link the button should open, or clear the label.')
            ok = False
        if url and not label:
            self.cta_label.errors.append('Add a short label for the button, or clear the link.')
            ok = False
        return ok


def _clean(value):
    return (value or '').strip()


def _fill(campaign, form):
    campaign.subject = _clean(form.subject.data)
    campaign.preview_text = _clean(form.preview_text.data) or None
    campaign.body_text = (form.body_text.data or '').strip()
    campaign.cta_label = _clean(form.cta_label.data) or None
    campaign.cta_url = _clean(form.cta_url.data) or None


def _render(campaign, mode):
    return render_email(
        subject=campaign.subject, body_text=campaign.body_text,
        preview_text=campaign.preview_text or '', cta_label=campaign.cta_label or '',
        cta_url=campaign.cta_url or '', mode=mode,
    )


def _render_form(form):
    """Preview of whatever is currently in the form (valid or not)."""
    return render_email(
        subject=_clean(form.subject.data), body_text=(form.body_text.data or '')[:BODY_MAX],
        preview_text=_clean(form.preview_text.data), cta_label=_clean(form.cta_label.data),
        cta_url=_clean(form.cta_url.data), mode='preview',
    )


def _transition(campaign_id, new_status, from_statuses, *extra_filters, **fields):
    """Atomic status change: one conditional UPDATE, True only if this call
    made the transition."""
    values = {'status': new_status}
    values.update(fields)
    updated = NewsletterCampaign.query.filter(
        NewsletterCampaign.id == campaign_id,
        NewsletterCampaign.status.in_(from_statuses),
        *extra_filters,
    ).update(values, synchronize_session=False)
    db.session.commit()
    return updated > 0


def _get_or_404(campaign_id):
    campaign = db.session.get(NewsletterCampaign, campaign_id)
    if campaign is None:
        abort(404)
    return campaign


def _is_stuck(campaign):
    started = campaign.sending_started_at
    return campaign.status == 'sending' and (started is None or _utcnow() - started > STUCK_AFTER)


def newsletter_panel_context():
    """Template vars for the Resend status / not-connected panel; also used
    by the landing page in app/admin.py."""
    return {
        'nl_configured': provider.is_configured(),
        'nl_missing': provider.missing_keys(),
        'nl_env_keys': provider.ALL_ENV_KEYS,
        'nl_reply_to': provider.reply_to_for(current_user.email),
        'nl_from': provider.from_address(),
        'nl_integrations_url': integrations_url(),
    }


def integrations_url():
    """Link to the developer-only Integrations page, if it exists and the
    current admin may open it; else None (the panel then says to ask the
    developer)."""
    if getattr(current_user, 'role', None) != 'developer':
        return None
    for endpoint in ('admin.integrations', 'admin.integrations_settings', 'admin.integrations_page'):
        if endpoint in current_app.view_functions:
            return url_for(endpoint)
    return None


# ============ COMPOSE / EDIT ============

def _compose(campaign=None):
    form = NewsletterForm(obj=campaign)
    action = request.form.get('action', 'save')
    if request.method == 'POST' and action == 'save' and form.validate_on_submit():
        if campaign is None:
            campaign = NewsletterCampaign(status='draft', author_admin_id=current_user.id,
                                          provider=PROVIDER)
            db.session.add(campaign)
        _fill(campaign, form)
        db.session.commit()
        flash('Draft saved.', 'success')
        return redirect(url_for('admin.newsletter_detail', campaign_id=campaign.id))
    # GET, a no-JS "Update preview" click, or a form with errors: re-render
    # with the preview built from the current field values.
    preview_html = _render_form(form) if (form.subject.data or form.body_text.data) else render_email(
        subject='Your subject line',
        body_text='Start typing your message on the left and the preview updates here.',
        mode='preview')
    return render_template(
        'admin/newsletter_compose.html', form=form, campaign=campaign,
        preview_html=preview_html, subscriber_count=NewsletterSubscriber.query.count(),
        **newsletter_panel_context()
    )


@admin_bp.route('/newsletter/compose', methods=['GET', 'POST'])
@admin_required
@permission_required('newsletter')
def newsletter_compose():
    return _compose()


@admin_bp.route('/newsletter/<int:campaign_id>/edit', methods=['GET', 'POST'])
@admin_required
@permission_required('newsletter')
def newsletter_edit(campaign_id):
    campaign = _get_or_404(campaign_id)
    if campaign.status not in EDITABLE:
        flash('This newsletter has already been sent, so it can no longer be edited.', 'warning')
        return redirect(url_for('admin.newsletter_detail', campaign_id=campaign.id))
    return _compose(campaign)


@admin_bp.route('/newsletter/preview', methods=['POST'])
@limiter.limit('60 per minute')
@admin_required
@permission_required('newsletter')
def newsletter_preview():
    """Live preview for the compose page (CSRF-protected POST). Returns the
    email HTML, which the page drops into a sandboxed iframe's srcdoc."""
    form = NewsletterForm(meta={'csrf': False})  # CSRFProtect already checked the token
    return Response(_render_form(form), mimetype='text/html')


# ============ REVIEW / TEST / SEND ============

@admin_bp.route('/newsletter/<int:campaign_id>')
@admin_required
@permission_required('newsletter')
def newsletter_detail(campaign_id):
    campaign = _get_or_404(campaign_id)
    return render_template(
        'admin/newsletter_detail.html', campaign=campaign,
        editable=campaign.status in EDITABLE, stuck=_is_stuck(campaign),
        preview_html=_render(campaign, 'preview'),
        subscriber_count=NewsletterSubscriber.query.count(),
        **newsletter_panel_context()
    )


@admin_bp.route('/newsletter/<int:campaign_id>/test', methods=['POST'])
@limiter.limit('5 per minute; 20 per hour')
@admin_required
@permission_required('newsletter')
def newsletter_test(campaign_id):
    """Sends this newsletter's HTML to the logged-in admin only, as a plain
    Resend email (POST /emails) — no broadcast is created."""
    campaign = _get_or_404(campaign_id)
    back = redirect(url_for('admin.newsletter_detail', campaign_id=campaign.id))
    if not provider.is_configured():
        flash("Resend isn't connected yet, so test emails can't be sent.", 'warning')
        return back
    if campaign.status not in EDITABLE:
        flash('This newsletter has already gone out.', 'info')
        return back
    try:
        provider.send_test(current_user.email, campaign.subject, _render(campaign, 'test'),
                           provider.reply_to_for(current_user.email))
    except provider.NewsletterError as exc:
        flash(f'The test email could not be sent: {exc.detail}', 'danger')
        return back
    flash(f'Test email sent to {current_user.email}. It can take a minute to arrive.', 'success')
    return back


@admin_bp.route('/newsletter/<int:campaign_id>/confirm')
@admin_required
@permission_required('newsletter')
def newsletter_confirm(campaign_id):
    campaign = _get_or_404(campaign_id)
    if campaign.status not in EDITABLE:
        flash('This newsletter has already been sent or is sending now.', 'info')
        return redirect(url_for('admin.newsletter_detail', campaign_id=campaign.id))
    if not provider.is_configured():
        flash("Resend isn't connected yet, so newsletters can't be sent.", 'warning')
        return redirect(url_for('admin.newsletter_detail', campaign_id=campaign.id))
    audience_count, audience_error = None, None
    try:
        audience_count = provider.audience_count()
    except provider.NewsletterError as exc:
        audience_error = exc.detail
    return render_template(
        'admin/newsletter_confirm.html', campaign=campaign,
        subscriber_count=NewsletterSubscriber.query.count(),
        audience_count=audience_count, audience_error=audience_error,
        **newsletter_panel_context()
    )


def _ensure_broadcast(campaign, reply_to):
    """Create the Resend broadcast (draft) the first time, or update the
    existing draft with the current content. Returns its id."""
    html = _render(campaign, 'broadcast')
    name = f'TAG newsletter #{campaign.id}: {campaign.subject}'[:100]
    if campaign.provider_message_id:
        provider.update_broadcast(campaign.provider_message_id, campaign.subject, html, reply_to, name)
        return campaign.provider_message_id
    new_id = provider.create_broadcast(campaign.subject, html, reply_to, name)
    # Only one request can hold 'sending', so this is just belt-and-braces.
    NewsletterCampaign.query.filter(
        NewsletterCampaign.id == campaign.id,
        NewsletterCampaign.provider_message_id.is_(None),
    ).update({'provider_message_id': new_id, 'provider': PROVIDER}, synchronize_session=False)
    db.session.commit()
    db.session.refresh(campaign)
    return campaign.provider_message_id


@admin_bp.route('/newsletter/<int:campaign_id>/send', methods=['POST'])
@limiter.limit('3 per minute; 10 per hour')
@admin_required
@permission_required('newsletter')
def newsletter_send(campaign_id):
    campaign = _get_or_404(campaign_id)
    detail_url = url_for('admin.newsletter_detail', campaign_id=campaign.id)
    if not provider.is_configured():
        flash("Resend isn't connected yet, so newsletters can't be sent.", 'warning')
        return redirect(detail_url)
    if request.form.get('confirm') != 'yes':
        flash('Tick the confirmation box to send the newsletter.', 'warning')
        return redirect(url_for('admin.newsletter_confirm', campaign_id=campaign.id))

    # The lock: only one request can move this row out of draft/failed.
    if not _transition(campaign.id, 'sending', EDITABLE, error=None,
                       sending_started_at=_utcnow(), provider=PROVIDER):
        flash('This newsletter has already been sent or is sending now.', 'info')
        return redirect(detail_url)
    db.session.refresh(campaign)

    sync = None
    try:
        # A previous attempt may have failed *after* Resend accepted the
        # send (e.g. a timeout on the response) — check before sending again.
        if campaign.provider_message_id:
            existing = provider.get_broadcast(campaign.provider_message_id)
            if provider.broadcast_was_sent(existing):
                _transition(campaign.id, 'sent', ('sending',), sent_at=_utcnow())
                flash('Resend shows this newsletter was already sent.', 'info')
                return redirect(detail_url)

        emails = [row.email for row in NewsletterSubscriber.query.with_entities(NewsletterSubscriber.email)]
        sync = provider.sync_contacts(emails)
        if sync['errors']:
            current_app.logger.warning('Newsletter %s: %s subscriber(s) could not be synced to Resend',
                                       campaign.id, sync['errors'])

        broadcast_id = _ensure_broadcast(campaign, provider.reply_to_for(current_user.email))
        provider.send_broadcast(broadcast_id)
    except provider.NewsletterError as exc:
        _transition(campaign.id, 'failed', ('sending',), error=exc.detail[:2000])
        flash(f'The newsletter was not sent. Resend said: {exc.detail}', 'danger')
        return redirect(detail_url)
    except Exception:
        current_app.logger.exception('Newsletter %s: unexpected error while sending', campaign.id)
        db.session.rollback()
        _transition(campaign.id, 'failed', ('sending',), error='Unexpected server error while sending.')
        flash('Something went wrong while sending. Nothing was marked as sent; please try again.', 'danger')
        return redirect(detail_url)

    # Resend sends to every subscribed (not opted-out) contact in the
    # segment; this is our best local estimate of that number.
    recipients = len(emails) - sync['skipped_unsubscribed'] - sync['errors']
    _transition(campaign.id, 'sent', ('sending',), sent_at=_utcnow(), recipient_count=max(recipients, 0))
    msg = 'Newsletter handed to Resend for delivery to all subscribers.'
    if sync['new'] or sync['added']:
        n = sync['new'] + sync['added']
        msg += f' {n} new website sign-up{"s were" if n != 1 else " was"} added to the Resend audience first.'
    flash(msg, 'success')
    return redirect(detail_url)


@admin_bp.route('/newsletter/<int:campaign_id>/unstick', methods=['POST'])
@limiter.limit('10 per hour')
@admin_required
@permission_required('newsletter')
def newsletter_unstick(campaign_id):
    """Recovery for a newsletter left in 'sending' (e.g. the server died
    mid-send). Only after 15 minutes, and only after asking Resend: if the
    broadcast actually went out it's marked sent, otherwise 'failed' so it
    can be edited and sent again. Both moves are conditional UPDATEs."""
    campaign = _get_or_404(campaign_id)
    detail_url = url_for('admin.newsletter_detail', campaign_id=campaign.id)
    if not _is_stuck(campaign):
        flash('Only a newsletter that has been "sending" for over 15 minutes can be reset.', 'warning')
        return redirect(detail_url)

    if campaign.provider_message_id:
        try:
            data = provider.get_broadcast(campaign.provider_message_id)
        except provider.NewsletterError as exc:
            flash(f"Couldn't check with Resend, so nothing was changed: {exc.detail}", 'danger')
            return redirect(detail_url)
        if provider.broadcast_was_sent(data):
            _transition(campaign.id, 'sent', ('sending',), sent_at=_utcnow())
            flash('Resend shows this newsletter did go out, so it is now marked as sent.', 'info')
            return redirect(detail_url)

    cutoff = _utcnow() - STUCK_AFTER
    done = _transition(
        campaign.id, 'failed', ('sending',),
        db.or_(NewsletterCampaign.sending_started_at.is_(None),
               NewsletterCampaign.sending_started_at < cutoff),
        error='Sending was interrupted and has been reset. Nothing was sent.',
    )
    flash('Marked as not sent. You can review it and send again.' if done
          else 'The newsletter changed while you were looking; nothing was reset.',
          'success' if done else 'warning')
    return redirect(detail_url)


@admin_bp.route('/newsletter/<int:campaign_id>/delete', methods=['POST'])
@admin_required
@permission_required('newsletter')
def newsletter_delete(campaign_id):
    """Deletes one draft (a single row nothing else references). Sent and
    sending newsletters are kept as history."""
    campaign = _get_or_404(campaign_id)
    if campaign.status not in EDITABLE:
        flash('Sent newsletters are kept as history and can\'t be deleted.', 'warning')
        return redirect(url_for('admin.newsletter_detail', campaign_id=campaign.id))
    broadcast_id = campaign.provider_message_id
    deleted = NewsletterCampaign.query.filter(
        NewsletterCampaign.id == campaign.id, NewsletterCampaign.status.in_(EDITABLE)
    ).delete(synchronize_session=False)
    db.session.commit()
    if deleted and broadcast_id and provider.is_configured():
        try:
            provider.delete_broadcast(broadcast_id)  # its unsent Resend draft, best effort
        except provider.NewsletterError:
            pass
    flash('Draft deleted.' if deleted else 'That newsletter is being sent and can\'t be deleted.',
          'success' if deleted else 'warning')
    return redirect(url_for('admin.newsletter_subscribers_list'))


def recent_campaigns(limit=25):
    """For the Newsletter landing page's campaign history."""
    return (NewsletterCampaign.query
            .order_by(NewsletterCampaign.created_at.desc(), NewsletterCampaign.id.desc())
            .limit(limit).all())
