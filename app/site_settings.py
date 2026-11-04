"""
Editable site information (phone, email, service times, social links...).

Storage is the key/value `site_settings` table (one row per field, value
JSON-encoded; see init_db.py / app/models.py::SiteSetting). Anything not
in the table falls back to DEFAULTS below, which are the values the site
shipped with (the old CHURCH_INFO dict + strings that were hardcoded in
templates). If the table is empty or the database is unreachable the site
renders with DEFAULTS — it never 500s because of settings.

`get_church_info()` is what templates see as `church_info` (injected for
every template by the context processor in app/__init__.py). It is cached
(Flask-Caching) and invalidated by `save_settings()`.

Only the developer and pastor roles may edit these (app/admin_site_settings.py).
"""

import json
import re
from urllib.parse import urlparse

from app import cache, db

CACHE_KEY = 'site_settings:church_info:v1'
CACHE_TIMEOUT = 600

DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
_DAY_ABBR = {'Sunday': 'Su', 'Monday': 'Mo', 'Tuesday': 'Tu', 'Wednesday': 'We',
             'Thursday': 'Th', 'Friday': 'Fr', 'Saturday': 'Sa'}

# Social platforms: key -> (label, Font Awesome icon class, allowed hosts).
# A URL is accepted only if its host is one of these or a subdomain of one.
SOCIAL_PLATFORMS = [
    ('facebook', 'Facebook', 'fa-brands fa-facebook-f', ('facebook.com', 'fb.com', 'fb.me')),
    ('instagram', 'Instagram', 'fa-brands fa-instagram', ('instagram.com',)),
    ('youtube', 'YouTube', 'fa-brands fa-youtube', ('youtube.com', 'youtu.be')),
    ('tiktok', 'TikTok', 'fa-brands fa-tiktok', ('tiktok.com',)),
    ('x', 'X (Twitter)', 'fa-brands fa-x-twitter', ('x.com', 'twitter.com')),
    ('whatsapp_channel', 'WhatsApp channel', 'fa-brands fa-whatsapp', ('whatsapp.com', 'wa.me')),
]
SOCIAL_KEYS = [p[0] for p in SOCIAL_PLATFORMS]

# Defaults = what the site showed before this feature existed. Social links
# are blank: the old templates only linked to the platforms' home pages
# (facebook.com etc.), not real church accounts.
DEFAULTS = {
    'name': 'Triumphant Assemblies of God (TAG)',
    'tagline': 'A Place of Triumph, Love & Purpose',
    'address': 'Dansoman, between Atomic and Glefe, Accra, Ghana',
    'digital_address': 'GA-570-0529',
    'phone': '0501116130',
    'phone_alt': '',
    'whatsapp': '0501116130',
    'email': 'triumphantag@gmail.com',
    'office_hours': 'Monday – Friday: 10:00 AM – 5:00 PM\nSaturday: 10:00 AM – 2:00 PM',
    'maps_query': 'Triumphant Assemblies of God Ghana, Zuman, Accra, Ghana',
    'giving_note': '',
    'footer_about': ('A Place of Triumph, Love & Purpose. Serving the people of Accra, Ghana, '
                     'and the nations since 1998 through the power of the Holy Spirit.'),
    'service_times': [
        {'day': 'Sunday', 'name': 'Joint Service', 'start': '07:00', 'end': '10:30', 'note': ''},
        {'day': 'Monday', 'name': 'Women Fellowship', 'start': '19:00', 'end': '', 'note': ''},
        {'day': 'Tuesday', 'name': 'Bible Studies', 'start': '19:00', 'end': '', 'note': ''},
        {'day': 'Wednesday', 'name': 'Prayer Service', 'start': '19:00', 'end': '', 'note': ''},
        {'day': 'Thursday', 'name': 'Youth Meeting', 'start': '19:00', 'end': '', 'note': ''},
    ],
    'social_facebook': '',
    'social_instagram': '',
    'social_youtube': '',
    'social_tiktok': '',
    'social_x': '',
    'social_whatsapp_channel': '',
}
SETTING_KEYS = list(DEFAULTS.keys())

FIELD_LABELS = {
    'name': 'Church name', 'tagline': 'Tagline', 'address': 'Address',
    'digital_address': 'Digital address', 'phone': 'Phone', 'phone_alt': 'Second phone',
    'whatsapp': 'WhatsApp number', 'email': 'Email', 'office_hours': 'Office hours',
    'maps_query': 'Google Maps search', 'giving_note': 'Giving details',
    'footer_about': 'Footer about text', 'service_times': 'Service times',
    **{f'social_{k}': label for k, label, _, _ in SOCIAL_PLATFORMS},
}

MAX_LENGTHS = {
    'name': 150, 'tagline': 150, 'address': 255, 'digital_address': 40,
    'phone': 30, 'phone_alt': 30, 'whatsapp': 30, 'email': 255,
    'office_hours': 500, 'maps_query': 255, 'giving_note': 1000, 'footer_about': 500,
    **{f'social_{k}': 500 for k in SOCIAL_KEYS},
}
MAX_SERVICE_ROWS = 20
SERVICE_NAME_MAX = 80
SERVICE_NOTE_MAX = 120


# ============ VALIDATION / NORMALISATION HELPERS ============

TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def normalize_phone(raw):
    """Return the E.164 form ('+233501116130') of a phone number, or None if
    it isn't one. Accepts Ghana local (0XX XXX XXXX), 233..., +233... and
    00233... forms with spaces/dashes/dots/brackets, and other +country
    numbers (8-15 digits)."""
    if not raw:
        return None
    s = re.sub(r'[\s\-().]', '', str(raw))
    if s.startswith('00'):
        s = '+' + s[2:]
    if re.fullmatch(r'0\d{9}', s):
        return '+233' + s[1:]
    if re.fullmatch(r'233\d{9}', s):
        return '+' + s
    if re.fullmatch(r'\+233\d{9}', s):
        return s
    if s.startswith('+233'):
        return None  # wrong digit count for a Ghana number
    if re.fullmatch(r'\+[1-9]\d{7,14}', s):
        return s
    return None


def format_phone(raw):
    """Human display form: '+233 50 111 6130' for Ghana numbers, E.164
    otherwise; the raw text if it can't be parsed."""
    e164 = normalize_phone(raw)
    if not e164:
        return (raw or '').strip()
    if e164.startswith('+233') and len(e164) == 13:
        d = e164[4:]
        return f'+233 {d[:2]} {d[2:5]} {d[5:]}'
    return e164


def social_url_error(key, url):
    """None if `url` is an acceptable link for platform `key`, else a message."""
    platform = next((p for p in SOCIAL_PLATFORMS if p[0] == key), None)
    if platform is None:
        return 'Unknown platform.'
    _, label, _, hosts = platform
    try:
        parsed = urlparse(url)
    except ValueError:
        return 'Enter a valid web address.'
    if parsed.scheme not in ('http', 'https'):
        return 'The link must start with https:// (or http://).'
    host = (parsed.hostname or '').lower()
    if not host or '@' in parsed.netloc or parsed.port not in (None, 80, 443):
        return 'Enter a valid web address.'
    if not any(host == h or host.endswith('.' + h) for h in hosts):
        return f'{label} links must be on {" or ".join(hosts)}.'
    return None


def _time_12h(hhmm):
    h, m = (int(x) for x in hhmm.split(':'))
    return f'{h % 12 or 12}:{m:02d}', ('AM' if h < 12 else 'PM')


def service_time_display(start, end=''):
    """'7:00 – 10:30 AM', '11:00 AM – 1:00 PM' or '7:00 PM'."""
    if not start or not TIME_RE.match(start):
        return ''
    s, s_mer = _time_12h(start)
    if end and TIME_RE.match(end):
        e, e_mer = _time_12h(end)
        if s_mer == e_mer:
            return f'{s} – {e} {e_mer}'
        return f'{s} {s_mer} – {e} {e_mer}'
    return f'{s} {s_mer}'


def clean_service_times(rows):
    """Keep only well-formed rows (used on read, so a hand-edited DB value
    can't break rendering)."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        day, start = r.get('day'), r.get('start') or ''
        if day not in DAYS or not TIME_RE.match(start):
            continue
        end = r.get('end') or ''
        out.append({
            'day': day,
            'name': str(r.get('name') or '')[:SERVICE_NAME_MAX],
            'start': start,
            'end': end if TIME_RE.match(end) else '',
            'note': str(r.get('note') or '')[:SERVICE_NOTE_MAX],
        })
    return out[:MAX_SERVICE_ROWS]


# ============ STORAGE ============

def load_raw_settings():
    """Effective editable values: DEFAULTS overlaid with whatever is stored.
    Not cached — the admin form reads this. Raises on DB errors."""
    from app.models import SiteSetting
    values = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    for row in SiteSetting.query.all():
        if row.setting_key not in DEFAULTS:
            continue
        try:
            value = json.loads(row.setting_value) if row.setting_value is not None else None
        except (TypeError, ValueError):
            continue
        if row.setting_key == 'service_times':
            if isinstance(value, list):
                values['service_times'] = clean_service_times(value)
        elif isinstance(value, str):
            values[row.setting_key] = value
    return values


def build_church_info(values):
    """Template-facing dict. Keeps the old CHURCH_INFO keys (name, address,
    digital_address, email, phone, service_times[{day, times}]) and adds
    derived, ready-to-use link values."""
    services = []
    for r in clean_service_times(values.get('service_times')):
        services.append({**r, 'time_display': service_time_display(r['start'], r['end']),
                         'start_display': service_time_display(r['start'])})
    legacy_times = []
    for s in services:
        if legacy_times and legacy_times[-1]['day'] == s['day']:
            legacy_times[-1]['times'].append(s['start_display'])
        else:
            legacy_times.append({'day': s['day'], 'times': [s['start_display']]})
    opening_hours = [
        f"{_DAY_ABBR[s['day']]} {s['start']}" + (f"-{s['end']}" if s['end'] else '')
        for s in services
    ]

    phone_e164 = normalize_phone(values.get('phone'))
    alt_e164 = normalize_phone(values.get('phone_alt'))
    wa_e164 = normalize_phone(values.get('whatsapp'))

    socials, social = [], {}
    for key, label, icon, _ in SOCIAL_PLATFORMS:
        url = (values.get(f'social_{key}') or '').strip()
        if url and social_url_error(key, url) is None:
            social[key] = url
            socials.append({'key': key, 'label': label, 'icon': icon, 'url': url})

    office = values.get('office_hours') or ''
    return {
        'name': values.get('name') or DEFAULTS['name'],
        'tagline': values.get('tagline') or '',
        'address': values.get('address') or DEFAULTS['address'],
        'digital_address': values.get('digital_address') or '',
        'email': values.get('email') or '',
        'phone': format_phone(values.get('phone')),
        'phone_tel': phone_e164 or '',
        'phone_alt': format_phone(values.get('phone_alt')) if values.get('phone_alt') else '',
        'phone_alt_tel': alt_e164 or '',
        'whatsapp': format_phone(values.get('whatsapp')) if values.get('whatsapp') else '',
        'whatsapp_url': f'https://wa.me/{wa_e164[1:]}' if wa_e164 else '',
        'service_times': legacy_times,
        'services': services,
        'sunday_service': next((s for s in services if s['day'] == 'Sunday'), None),
        'opening_hours': opening_hours,
        'office_hours': office,
        'office_hours_lines': [ln.strip() for ln in office.splitlines() if ln.strip()],
        'maps_query': values.get('maps_query') or DEFAULTS['maps_query'],
        'giving_note': values.get('giving_note') or '',
        'giving_note_lines': [ln.strip() for ln in (values.get('giving_note') or '').splitlines() if ln.strip()],
        'footer_about': values.get('footer_about') or '',
        'socials': socials,
        'social': social,
    }


def default_church_info():
    return build_church_info(DEFAULTS)


def get_church_info():
    """Cached `church_info` for templates. Falls back to DEFAULTS (uncached)
    if the settings table can't be read."""
    try:
        info = cache.get(CACHE_KEY)
    except Exception:
        info = None
    if info is not None:
        return info
    try:
        info = build_church_info(load_raw_settings())
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return default_church_info()
    try:
        cache.set(CACHE_KEY, info, timeout=CACHE_TIMEOUT)
    except Exception:
        pass
    return info


def invalidate_cache():
    try:
        cache.delete(CACHE_KEY)
    except Exception:
        pass


def save_settings(new_values, admin):
    """Persist only the keys whose value changed (one row per key, upsert),
    write one audit row listing them, commit, and drop the cache. Returns
    the list of changed keys."""
    from datetime import datetime
    from app.models import SiteSetting, SiteSettingsLog
    current = load_raw_settings()
    changed = [k for k in SETTING_KEYS if k in new_values and new_values[k] != current.get(k)]
    if not changed:
        return []
    now = datetime.utcnow()
    for key in changed:
        encoded = json.dumps(new_values[key], ensure_ascii=False)
        row = db.session.get(SiteSetting, key)
        if row is None:
            db.session.add(SiteSetting(setting_key=key, setting_value=encoded,
                                       updated_at=now, updated_by_id=admin.id))
        else:
            row.setting_value = encoded
            row.updated_at = now
            row.updated_by_id = admin.id
    db.session.add(SiteSettingsLog(
        admin_id=admin.id, changed_at=now,
        changed_fields=', '.join(FIELD_LABELS.get(k, k) for k in changed)[:1000],
    ))
    db.session.commit()
    invalidate_cache()
    return changed
