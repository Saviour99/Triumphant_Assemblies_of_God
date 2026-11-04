"""
Turns a newsletter written in plain text into the designed HTML email
(app/templates/email/newsletter.html).

Writing rules (shown to the admin on the compose page):
    - a blank line starts a new paragraph
    - lines starting with "- " become bullet points
    - bare http(s):// links become clickable
    - **double asterisks** make text bold

Safety: every piece of user text is HTML-escaped with markupsafe.escape
*before* any markup is added, and the only markup ever produced is the
fixed set of tags below — so <script> etc. in the body comes out as
inert text, both in the admin preview and in the sent email.
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import render_template, url_for
from markupsafe import Markup, escape

# Only http(s) URLs are ever linked: the scheme is part of the pattern, so
# javascript:/data:/vbscript: text is never matched and stays plain text.
# The URL stops at whitespace, quotes and angle brackets, so it can't break
# out of the href attribute (and Markup.format escapes it again anyway).
URL_RE = re.compile(r'https?://[^\s<>"\'`]+', re.IGNORECASE)
BOLD_RE = re.compile(r'\*\*(.+?)\*\*')
TRAILING_PUNCT = '.,;:!?)]}'

# --- Markup audit (bandit B704) ---------------------------------------
# Markup(...) is only ever called on the string *literals* below. Every
# piece of user text reaches HTML through Markup.format()/Markup.join(),
# which run markupsafe.escape() on each non-Markup argument, or through an
# explicit escape() call. Nothing user-supplied is ever wrapped in Markup().
# Inline styles: email clients strip <style> blocks unpredictably, so the
# look lives on each element.
P_TAG = Markup('<p style="margin:0 0 18px 0;font-family:Georgia,\'Times New Roman\',serif;'
               'font-size:17px;line-height:1.65;color:#2B3345;">{0}</p>')
UL_TAG = Markup('<ul style="margin:0 0 18px 0;padding:0 0 0 22px;font-family:Georgia,\'Times New Roman\',serif;'
                'font-size:17px;line-height:1.65;color:#2B3345;">{0}</ul>')
LI_TAG = Markup('<li style="margin:0 0 8px 0;padding:0;">{0}</li>')
A_TAG = Markup('<a href="{0}" style="color:#0D2B6B;text-decoration:underline;" target="_blank">{1}</a>')
STRONG_TAG = Markup('<strong>{0}</strong>')
BR = Markup('<br>')
EMPTY = Markup('')
NEWLINE = Markup('\n')


def is_http_url(value):
    """True only for absolute http(s) URLs with a host."""
    try:
        parts = urlsplit((value or '').strip())
    except ValueError:
        return False
    return parts.scheme in ('http', 'https') and bool(parts.netloc)


def _format_text(text):
    """Plain text -> Markup, with **bold**. Each piece is escaped by
    Markup.format/join; the only tag added is the literal <strong>."""
    out = []
    pos = 0
    for m in BOLD_RE.finditer(text):
        out.append(escape(text[pos:m.start()]))
        out.append(STRONG_TAG.format(m.group(1)))
        pos = m.end()
    out.append(escape(text[pos:]))
    return EMPTY.join(out)


def _format_inline(line):
    """One line of user text -> safe Markup with links and bold."""
    out = []
    pos = 0
    for m in URL_RE.finditer(line):
        url = m.group(0)
        trail = ''
        while url and url[-1] in TRAILING_PUNCT:
            trail = url[-1] + trail
            url = url[:-1]
        out.append(_format_text(line[pos:m.start()]))
        if is_http_url(url):
            out.append(A_TAG.format(url, url))  # both escaped by format()
        else:
            out.append(escape(url))
        out.append(escape(trail))
        pos = m.end()
    out.append(_format_text(line[pos:]))
    return EMPTY.join(out)


def format_body(text):
    """Plain text -> Markup of <p>/<ul> blocks with inline styles."""
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n[ \t]*\n', text)
    html = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.split('\n') if ln.strip()]
        if not lines:
            continue
        # Group consecutive bullet lines into one list; other lines in the
        # same block become one paragraph with line breaks.
        para, bullets = [], []

        def flush_para():
            if para:
                html.append(P_TAG.format(BR.join(_format_inline(p) for p in para)))
                para.clear()

        def flush_bullets():
            if bullets:
                items = EMPTY.join(LI_TAG.format(_format_inline(b)) for b in bullets)
                html.append(UL_TAG.format(items))
                bullets.clear()

        for ln in lines:
            stripped = ln.lstrip()
            if stripped.startswith('- '):
                flush_para()
                bullets.append(stripped[2:].strip())
            else:
                flush_bullets()
                para.append(stripped)
        flush_para()
        flush_bullets()
    return NEWLINE.join(html)


def render_email(subject, body_text, preview_text='', cta_label='', cta_url='',
                 mode='preview'):
    """Render the full email HTML.

    mode='broadcast' (what Resend receives for the real send): images use
    absolute URLs built from SITE_URL — never from request.host, which a
    client can spoof — and the unsubscribe link is Resend's per-recipient
    placeholder {{{RESEND_UNSUBSCRIBE_URL}}}.

    mode='test' (the "send a test to me" email): same as broadcast, but a
    plain transactional email has no unsubscribe placeholder substitution,
    so the link points at the website instead.

    mode='preview' (the admin's in-page preview): unsubscribe is a dummy
    link, and if SITE_URL isn't set yet the logo falls back to a
    site-relative URL (it's shown inside an iframe srcdoc on our own admin
    page, which resolves it against our origin).
    """
    from app.newsletter_resend import site_url, UNSUBSCRIBE_PLACEHOLDER

    base = site_url()
    logo_path = url_for('static', filename='img/logo2.png')
    logo_url = (base + logo_path) if base else logo_path

    if mode == 'broadcast':
        unsubscribe_url = UNSUBSCRIBE_PLACEHOLDER
    elif mode == 'test':
        unsubscribe_url = base or '#'
    else:
        unsubscribe_url = '#'

    cta_ok = bool(cta_label and cta_url and is_http_url(cta_url))
    return render_template(
        'email/newsletter.html',
        subject=subject or 'Untitled newsletter',
        preview_text=preview_text or '',
        body_html=format_body(body_text),
        cta_label=cta_label if cta_ok else '',
        cta_url=cta_url if cta_ok else '',
        logo_url=logo_url,
        site_url=base,
        unsubscribe_url=unsubscribe_url,
        year=datetime.now(timezone.utc).year,
    )
