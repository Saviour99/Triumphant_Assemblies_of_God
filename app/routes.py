import hashlib
import hmac
import uuid

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, Response
from app import db, cache, csrf, limiter
from app.models import (
    PrayerRequest, ContactMessage, NewsletterSubscriber, Giving,
    VideoSermon, AudioSermon, Devotion, Ebook, Testimony
)
from app.utils import get_ebooks_by_category, get_testimonies, validate_email, sanitize_text as sanitize_input
from app.security import site_base_url
from app.email_utils import notify_church
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, date
from sqlalchemy import or_
import re

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

from app.site_settings import get_church_info  # noqa: E402

# Legacy static church data. The live values are admin-editable
# (/admin/site-settings, app/site_settings.py) and reach templates via
# get_church_info(); app/site_settings.py::DEFAULTS is the fallback.
# Kept for any old import of CHURCH_INFO; routes no longer render it.
CHURCH_INFO = {
    'name': 'Triumphant Assemblies of God (TAG)',
    'address': 'Dansoman, between Atomic and Glefe, Accra, Ghana',
    'digital_address': 'GA-570-0529',
    'email': 'triumphantag@gmail.com',
    'phone': '0501116130',
    'service_times': [
        {'day': 'Sunday', 'times': ['7:00 AM', '9:30 AM']},
        {'day': 'Wednesday', 'times': ['6:00 PM']}
    ]
}

LEADERSHIP = [
    {
        'name': 'Rev. Rexford Peprah',
        'title': 'Senior Pastor',
        'bio': 'Rev. Rexford Peprah is a seasoned minister of the Gospel, dynamic leader, author, conference speaker, and church administrator with a passion for spiritual growth, leadership development, and transformational ministry. He holds a Master of Arts in Biblical Studies from Global University, USA, and an MBA in Finance from the University of Ghana, Legon.',
        'image': 'pastor.jpg'
    },
    {
        'name': 'Deacon James Larry Gordor',
        'title': 'Deacon of Hospitality & Church Secretary',
        'bio': 'Deacon James Larry Gordor is a dedicated servant of God and faithful leader at TAG, where he supports the smooth administration of the church and helps create a welcoming, orderly, and hospitable environment for members, visitors, and guests.',
        'image': 'deacon1.jpg'
    },
    {
        'name': 'Deacon Daniel Baah-Agyare',
        'title': 'Youth Ministry Liaison',
        'bio': 'Deacon Daniel Baah-Agyare is devoted to serving the church with humility, faithfulness, and dedication, supporting both the spiritual and administrative life of the ministry. He works closely with church leaders to promote unity and represent the interests of the youth ministry.',
        'image': 'deacon2.jpg'
    },
    {
        'name': 'Mrs. Evelyn Gbagbo',
        'title': 'Deaconess & Women\'s Ministry Liaison',
        'bio': 'Mrs. Evelyn Gbagbo is a devoted servant of God, committed church leader, and faithful member of the TAG Church Board. She plays a key role in facilitating, organizing, and administering the Children\'s Ministry and serves as the Church Treasurer.',
        'image': 'deaconess.jpg'
    }
]

MINISTRIES = [
    {
        'name': 'Children\'s Ministry',
        'icon': 'fa-child',
        'description': 'Nurturing young hearts in the knowledge and love of Christ through age-appropriate programs, activities, and spiritual guidance.',
        'contact': 'children@triumphantag.com'
    },
    {
        'name': 'Youth Ministry',
        'icon': 'fa-users',
        'description': 'Empowering young adults to grow in faith, develop leadership skills, and serve the community with purpose and passion.',
        'contact': 'youth@triumphantag.com'
    },
    {
        'name': 'Women\'s Fellowship',
        'icon': 'fa-female',
        'description': 'A supportive community for women to grow spiritually, share experiences, and serve together in various church initiatives.',
        'contact': 'women@triumphantag.com'
    },
    {
        'name': 'Men\'s Fellowship',
        'icon': 'fa-male',
        'description': 'Building strong men of faith through prayer, study, and service to strengthen families and the church community.',
        'contact': 'men@triumphantag.com'
    },
    {
        'name': 'Praises & Worship Team',
        'icon': 'fa-music',
        'description': 'Leading the congregation in spirit-filled worship through music, praise, and creating an atmosphere for God\'s presence.',
        'contact': 'worship@triumphantag.com'
    },
    {
        'name': 'Outreach & Missions',
        'icon': 'fa-globe',
        'description': 'Extending God\'s love and compassion to the community and beyond through evangelism, community service, and mission work.',
        'contact': 'missions@triumphantag.com'
    }
]

# ============ MAIN ROUTES ============

@main_bp.route('/')
def index():
    """Home page"""
    return render_template('public/index.html', church_info=get_church_info())

@main_bp.route('/about')
def about():
    """About page"""
    vision = "To be a thriving, Spirit-empowered community that mirrors the first church: deeply rooted in God's presence, committed to genuine fellowship, and actively expanding God's Kingdom in our community and beyond."
    mission = "To lead individuals into a life-changing relationship with Jesus Christ, nurture them in faith and community, and equip them to serve with purpose."
    purpose = "To glorify God by becoming a beacon of hope, a center for spiritual growth, and a catalyst for transformative love in our families, community, and nation."
    
    core_values = [
        'Christ Above All: Making Jesus the undisputed center of our lives and decisions.',
        'Rooted in Truth: Living with integrity, guided by the authority of Scripture.',
        'One in Fellowship: Pursuing unity and celebrating diversity as one family in Christ.',
        'Generous in Service: Loving our neighbors through compassionate action and community impact.',
        'Driven by Excellence: Honoring God with our best in everything we do.',
        'Empowering Every Leader: Developing disciples to fulfill their God-given purpose.',
        'Building to Last: Stewarding resources for generational impact and a lasting legacy.'
    ]
    
    return render_template('public/about.html', 
                         vision=vision, 
                         mission=mission, 
                         purpose=purpose,
                         core_values=core_values,
                         leadership=LEADERSHIP,
                         church_info=get_church_info())

@main_bp.route('/ministries')
def ministries():
    """Ministries page"""
    return render_template('public/ministries.html', ministries=MINISTRIES, church_info=get_church_info())

@main_bp.route('/sermons')
def sermons():
    """Sermons page"""
    video_sermons = VideoSermon.query.order_by(VideoSermon.sermon_date.desc()).all()
    audio_sermons = AudioSermon.query.order_by(AudioSermon.sermon_date.desc()).all()
    return render_template(
        'public/sermons.html',
        video_sermons=video_sermons,
        audio_sermons=audio_sermons,
        church_info=get_church_info()
    )

@main_bp.route('/events')
def events():
    """Events page. Only published events; upcoming = starts now or later
    (soonest first), past = already started (most recent first, capped)."""
    from app.models import Event
    now = datetime.now()
    published = Event.query.filter(Event.is_published.is_(True))
    upcoming_events = published.filter(Event.start_at >= now).order_by(Event.start_at.asc()).all()
    past_events = published.filter(Event.start_at < now).order_by(Event.start_at.desc()).limit(12).all()
    return render_template(
        'public/events.html',
        upcoming_events=upcoming_events,
        past_events=past_events,
        church_info=get_church_info()
    )

@main_bp.route('/blog')
def blog():
    """Blog / daily devotion page"""
    requested_date = request.args.get('date')
    if requested_date:
        try:
            parsed_date = datetime.strptime(requested_date, '%Y-%m-%d').date()
        except ValueError:
            parsed_date = None
        devotion = Devotion.query.filter_by(devotion_date=parsed_date).first() if parsed_date else None
        if not devotion:
            devotion = Devotion.query.order_by(Devotion.devotion_date.desc()).first()
    else:
        devotion = Devotion.query.order_by(Devotion.devotion_date.desc()).first()

    past_devotions = Devotion.query.order_by(Devotion.devotion_date.desc()).limit(10).all()
    recent_testimonies = get_testimonies(limit=8)

    return render_template(
        'public/blog.html',
        devotion=devotion,
        past_devotions=past_devotions,
        recent_testimonies=recent_testimonies,
        church_info=get_church_info()
    )


@main_bp.route('/blog/devotionals')
def blog_devotionals():
    """Full devotion archive — every devotion ever posted, paginated."""
    page = request.args.get('page', 1, type=int)
    pagination = Devotion.query.order_by(Devotion.devotion_date.desc()).paginate(
        page=page, per_page=5, error_out=False
    )
    return render_template(
        'public/blog_devotionals.html',
        pagination=pagination,
        devotions=pagination.items,
        church_info=get_church_info()
    )


@main_bp.route('/blog/worship')
def blog_worship():
    """Worship reading list."""
    ebooks = get_ebooks_by_category('worship')
    return render_template('public/blog_ebooks.html', ebooks=ebooks, category='worship', church_info=get_church_info())


@main_bp.route('/blog/leadership')
def blog_leadership():
    """Leadership reading list."""
    ebooks = get_ebooks_by_category('leadership')
    return render_template('public/blog_ebooks.html', ebooks=ebooks, category='leadership', church_info=get_church_info())


@main_bp.route('/blog/testimonies')
def blog_testimonies():
    """Member testimonies (approved only) + the member submission form."""
    from app.testimony_submit import TestimonySubmitForm
    testimonies = get_testimonies()
    return render_template('public/blog_testimonies.html', testimonies=testimonies,
                           form=TestimonySubmitForm(), church_info=get_church_info())


DEVOTIONAL_SEARCH_KEYWORDS = {'devotional', 'devotionals', 'devotion', 'devotions'}
WORSHIP_SEARCH_KEYWORDS = {'worship'}
LEADERSHIP_SEARCH_KEYWORDS = {'leadership'}
TESTIMONY_SEARCH_KEYWORDS = {'testimonial', 'testimonials', 'testimony', 'testimonies'}


@main_bp.route('/blog/search')
def blog_search():
    """Unified search across devotions, e-books, and testimonies, used by
    the blog sidebar's search box. Typing a bare category name (e.g.
    "worship") lists everything in that category; anything else does a
    free-text match across each type's title/author/content fields."""
    query = request.args.get('q', '').strip()
    normalized = query.lower()

    devotions, ebooks, testimonies, category_label = [], [], [], None

    if not query:
        pass
    elif normalized in DEVOTIONAL_SEARCH_KEYWORDS:
        devotions = Devotion.query.order_by(Devotion.devotion_date.desc()).all()
        category_label = 'devotional'
    elif normalized in WORSHIP_SEARCH_KEYWORDS:
        ebooks = get_ebooks_by_category('worship')
        category_label = 'worship'
    elif normalized in LEADERSHIP_SEARCH_KEYWORDS:
        ebooks = get_ebooks_by_category('leadership')
        category_label = 'leadership'
    elif normalized in TESTIMONY_SEARCH_KEYWORDS:
        testimonies = get_testimonies()
        category_label = 'testimonies'
    else:
        like_pattern = f'%{query}%'
        devotions = Devotion.query.filter(
            or_(
                Devotion.title.ilike(like_pattern),
                Devotion.quote.ilike(like_pattern),
                Devotion.quote_theme.ilike(like_pattern),
                Devotion.reflection.ilike(like_pattern),
                Devotion.writer_name.ilike(like_pattern),
            )
        ).order_by(Devotion.devotion_date.desc()).all()

        ebooks = Ebook.query.filter(
            or_(
                Ebook.title.ilike(like_pattern),
                Ebook.author.ilike(like_pattern),
                Ebook.summary.ilike(like_pattern),
            )
        ).order_by(Ebook.title.asc()).all()

        testimonies = Testimony.query.filter(
            Testimony.status == 'approved',
            or_(
                Testimony.name.ilike(like_pattern),
                Testimony.testimony.ilike(like_pattern),
            )
        ).order_by(Testimony.created_at.desc()).all()

    return render_template(
        'public/blog_search.html',
        query=query,
        category_label=category_label,
        devotions=devotions,
        ebooks=ebooks,
        testimonies=testimonies,
        church_info=get_church_info()
    )


@main_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('public/contact.html', church_info=get_church_info())

@main_bp.route('/giving')
def giving():
    """Offering page"""
    return render_template('public/offering.html', church_info=get_church_info())

PAYSTACK_REFERENCE_RE = re.compile(r'[A-Za-z0-9_-]{1,100}')
GIVING_TYPE_LABELS = {
    'tithe': 'Tithe', 'offering': 'Offering', 'missions': 'Missions',
    'building_fund': 'Building Fund', 'other': 'Other',
}


def _accra_time(dt):
    """created_at is stored as naive UTC. Accra is UTC+0 year-round (no
    DST), but convert properly so this stays right if that ever changes."""
    if not dt:
        return None
    from datetime import timezone
    try:
        from zoneinfo import ZoneInfo
        return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Africa/Accra'))
    except Exception:
        return dt.replace(tzinfo=timezone.utc)


@main_bp.route('/giving/thank-you')
@limiter.limit('30 per minute;300 per hour')
def giving_thank_you():
    """Thank-you / receipt page the giving form redirects to after the
    Paystack popup. Looked up by the (uuid4, unguessable) Paystack reference.
    The template only ever receives the `gift` dict below: first name,
    amount, fund, date, status and reference. Never the email, full name
    or member record. Unknown and malformed references render the same
    generic state so the page can't be used to probe references."""
    reference = request.args.get('reference', '').strip()
    donation = None
    if PAYSTACK_REFERENCE_RE.fullmatch(reference):
        donation = Giving.query.filter_by(paystack_reference=reference).first()

    gift = None
    status = 'unknown'
    if donation:
        status = donation.status if donation.status in ('completed', 'pending') else 'failed'
        name_parts = (donation.donor_name or '').strip().split()
        gift = {
            'first_name': name_parts[0][:40] if name_parts else None,
            'amount': donation.amount,
            'fund': GIVING_TYPE_LABELS.get(donation.giving_type,
                                           (donation.giving_type or '').replace('_', ' ').title()),
            'given_at': _accra_time(donation.created_at),
            'reference': donation.paystack_reference,
        }

    response = Response(render_template(
        'public/payment_received.html',
        gift=gift, status=status, church_info=get_church_info()
    ))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response

@main_bp.route('/privacy-policy')
def privacy_policy():
    """Privacy policy page"""
    return render_template('public/privacy_policy.html', church_info=get_church_info())

@main_bp.route('/terms-and-conditions')
def terms():
    """Terms and conditions page"""
    return render_template('public/terms.html', church_info=get_church_info())


@main_bp.route('/robots.txt')
@cache.cached(timeout=3600)
def robots_txt():
    """Allow public pages, keep auth/dashboard areas out of the crawl."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /members/",
        "Disallow: /blog/search",
        f"Sitemap: {site_base_url()}/sitemap.xml",
    ]
    return Response("\n".join(lines) + "\n", mimetype='text/plain')


@main_bp.route('/sitemap.xml')
@cache.cached(timeout=3600)
def sitemap_xml():
    """Dynamically generated. Absolute URLs come from SITE_URL (falls back
    to the request root only in development), never the Host header — this
    response is cached, so a forged Host would otherwise poison it."""
    base = site_base_url()
    latest_devotion = Devotion.query.order_by(Devotion.devotion_date.desc()).first()
    devotion_lastmod = latest_devotion.devotion_date.isoformat() if latest_devotion else None

    pages = [
        {'loc': url_for('main.index'), 'changefreq': 'weekly', 'priority': '1.0'},
        {'loc': url_for('main.about'), 'changefreq': 'monthly', 'priority': '0.6'},
        {'loc': url_for('main.ministries'), 'changefreq': 'monthly', 'priority': '0.6'},
        {'loc': url_for('main.sermons'), 'changefreq': 'weekly', 'priority': '0.8'},
        {'loc': url_for('main.events'), 'changefreq': 'weekly', 'priority': '0.6'},
        {'loc': url_for('main.blog'), 'changefreq': 'daily', 'priority': '0.9', 'lastmod': devotion_lastmod},
        {'loc': url_for('main.blog_devotionals'), 'changefreq': 'daily', 'priority': '0.7', 'lastmod': devotion_lastmod},
        {'loc': url_for('main.blog_worship'), 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': url_for('main.blog_leadership'), 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': url_for('main.blog_testimonies'), 'changefreq': 'monthly', 'priority': '0.5'},
        {'loc': url_for('main.contact'), 'changefreq': 'yearly', 'priority': '0.5'},
        {'loc': url_for('main.giving'), 'changefreq': 'monthly', 'priority': '0.7'},
        {'loc': url_for('main.privacy_policy'), 'changefreq': 'yearly', 'priority': '0.3'},
        {'loc': url_for('main.terms'), 'changefreq': 'yearly', 'priority': '0.3'},
    ]

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for page in pages:
        xml_parts.append('<url>')
        xml_parts.append(f"<loc>{base}{page['loc']}</loc>")
        if page.get('lastmod'):
            xml_parts.append(f"<lastmod>{page['lastmod']}</lastmod>")
        xml_parts.append(f"<changefreq>{page['changefreq']}</changefreq>")
        xml_parts.append(f"<priority>{page['priority']}</priority>")
        xml_parts.append('</url>')
    xml_parts.append('</urlset>')

    return Response('\n'.join(xml_parts), mimetype='application/xml')


# ============ API ROUTES ============

@api_bp.route('/prayer-request', methods=['POST'])
@limiter.limit('3 per minute;15 per hour')
def prayer_request():
    """Handle prayer request submissions"""
    try:
        data = request.get_json(silent=True) or {}

        name = sanitize_input(data.get('name', ''))
        email = sanitize_input(data.get('email', ''))
        topic = sanitize_input(data.get('topic', ''))
        message = sanitize_input(data.get('message', ''))

        if not all([name, email, topic, message]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Please enter a valid, deliverable email address'}), 400

        if len(message) < 10:
            return jsonify({'success': False, 'message': 'Message must be at least 10 characters'}), 400

        db.session.add(PrayerRequest(name=name, email=email, topic=topic, message=message))
        db.session.commit()

        # Best-effort alert to MAIL_NOTIFY_TO (no-op if unset; never raises).
        notify_church(
            f'New prayer request: {topic}'[:150], 'New prayer request',
            [('Name', name), ('Email', email), ('Topic', topic), ('Request', message)],
            reply_to=email, category='prayer_request',
        )

        return jsonify({'success': True, 'message': 'Prayer request submitted successfully'}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'prayer_request error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


@api_bp.route('/contact-form', methods=['POST'])
@limiter.limit('3 per minute;15 per hour')
def contact_form():
    """Handle contact form submissions"""
    try:
        data = request.get_json(silent=True) or {}

        name = sanitize_input(data.get('name', ''))
        email = sanitize_input(data.get('email', ''))
        phone = sanitize_input(data.get('phone', ''))
        subject = sanitize_input(data.get('subject', ''))
        message = sanitize_input(data.get('message', ''))

        if not all([name, email, subject, message]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Please enter a valid, deliverable email address'}), 400

        db.session.add(ContactMessage(name=name, email=email, phone=phone or None, subject=subject, message=message))
        db.session.commit()

        # Best-effort alert to MAIL_NOTIFY_TO (no-op if unset; never raises).
        notify_church(
            f'New contact message: {subject}'[:150], 'New contact message',
            [('Name', name), ('Email', email), ('Phone', phone or '-'),
             ('Subject', subject), ('Message', message)],
            reply_to=email, category='contact_message',
        )

        return jsonify({'success': True, 'message': 'Message sent successfully'}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'contact_form error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


@api_bp.route('/newsletter', methods=['POST'])
@limiter.limit('3 per minute;10 per hour')
def newsletter():
    """Handle newsletter signup"""
    try:
        data = request.get_json(silent=True) or {}
        email = sanitize_input(data.get('email', ''))

        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400

        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Please enter a valid, deliverable email address'}), 400

        # Same answer whether or not the address was already subscribed, so
        # this endpoint can't be used to test who is on the mailing list.
        if not NewsletterSubscriber.query.filter_by(email=email).first():
            db.session.add(NewsletterSubscriber(email=email))
            db.session.commit()

        return jsonify({'success': True, 'message': "You're subscribed to our newsletter"}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'newsletter error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


# ============ GIVING / PAYSTACK ============

VALID_GIVING_TYPES = {'tithe', 'offering', 'missions', 'building_fund', 'other'}
MIN_GIVING_AMOUNT = Decimal('1.00')
MAX_GIVING_AMOUNT = Decimal('100000.00')
GIVING_CURRENCY = 'GHS'
# Paystack transaction statuses that are final failures. Anything else that
# isn't 'success' (ongoing, pending, processing, queued, API errors) may still
# succeed, so it must NOT mark the donation failed.
PAYSTACK_FINAL_FAILURE_STATUSES = {'failed', 'abandoned', 'reversed'}


def _expected_kobo(donation):
    return int((Decimal(donation.amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


@api_bp.route('/giving/init', methods=['POST'])
@limiter.limit('5 per minute;20 per hour')
def giving_init():
    """
    Step 1 of the Paystack flow: create a pending Giving row server-side
    (never trusting a client-supplied 'amount already paid' claim) and hand
    back a reference for the browser to open the Paystack popup with.
    """
    try:
        data = request.get_json(silent=True) or {}

        giving_type = sanitize_input(data.get('giving_type', ''))
        donor_name = sanitize_input(data.get('donor_name', ''))
        donor_email = sanitize_input(data.get('donor_email', ''))

        if giving_type not in VALID_GIVING_TYPES:
            return jsonify({'success': False, 'message': 'Invalid giving type'}), 400

        if not all([donor_name, donor_email]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if not validate_email(donor_email):
            return jsonify({'success': False, 'message': 'Please enter a valid, deliverable email address'}), 400

        try:
            amount = Decimal(str(data.get('amount')).strip()).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if not amount.is_finite() or amount < MIN_GIVING_AMOUNT or amount > MAX_GIVING_AMOUNT:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return jsonify({
                'success': False,
                'message': f'Please enter an amount between GH₵{MIN_GIVING_AMOUNT} and GH₵{MAX_GIVING_AMOUNT:,}'
            }), 400

        from flask_login import current_user
        from app.models import Member

        reference = uuid.uuid4().hex
        donation = Giving(
            amount=amount,
            giving_type=giving_type,
            donor_name=donor_name,
            donor_email=donor_email,
            paystack_reference=reference,
            status='pending',
            member_id=current_user.id if current_user.is_authenticated and isinstance(current_user, Member) else None
        )
        db.session.add(donation)
        db.session.commit()

        return jsonify({
            'success': True,
            'reference': reference,
            # The stored (quantized) amount — what Paystack must charge.
            'amount': float(donation.amount),
            'email': donor_email,
            'public_key': current_app.config.get('PAYSTACK_PUBLIC_KEY', '')
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'giving_init error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


def _set_donation_status_once(donation_id, new_status, from_statuses=('pending',)):
    """Atomically flip a donation's status with a single conditional UPDATE,
    instead of a Python-level read-then-write. This is what makes it safe
    for the client-triggered /paystack/verify call and the /paystack/webhook
    call to race each other (or either to be retried/duplicated) without
    ever double-processing or clobbering an already-completed donation back
    to 'failed'. Returns True only if this call performed the transition."""
    updated_rows = Giving.query.filter(
        Giving.id == donation_id, Giving.status.in_(from_statuses)
    ).update({'status': new_status}, synchronize_session=False)
    db.session.commit()
    return updated_rows > 0


def _verify_with_paystack(reference):
    """Calls Paystack's own verify-transaction API and returns (ok, payload)
    where ok is True only if Paystack confirms a successful charge. Shared
    by the client-triggered verify endpoint; the webhook doesn't need this
    round trip since the webhook signature is itself the trust mechanism."""
    import requests

    secret_key = current_app.config.get('PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        current_app.logger.error('PAYSTACK_SECRET_KEY is not configured')
        return None, None

    try:
        resp = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=10
        )
        payload = resp.json()
    except Exception as e:
        current_app.logger.error(f'paystack verify request error: {e}')
        return None, None

    if not isinstance(payload, dict):
        return None, None
    return payload, (payload.get('data') or {})


@api_bp.route('/paystack/verify', methods=['POST'])
@limiter.limit('10 per minute;60 per hour')
def paystack_verify():
    """
    Step 2 of the client-side flow: verify the transaction server-side
    against Paystack's API before ever marking a donation completed. The
    browser's callback is never trusted on its own. This is a best-effort
    path — if the browser never calls this (closed tab, dropped network),
    /api/paystack/webhook is the authoritative fallback that reconciles it.
    """
    reference = sanitize_input(str((request.get_json(silent=True) or {}).get('reference', '')))
    if not reference:
        return jsonify({'success': False, 'message': 'Missing reference'}), 400
    # References are generated by giving_init (uuid hex). Reject anything
    # else before it is interpolated into the Paystack API URL path.
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', reference):
        return jsonify({'success': False, 'message': 'Unknown transaction'}), 404

    donation = Giving.query.filter_by(paystack_reference=reference).first()
    if not donation:
        return jsonify({'success': False, 'message': 'Unknown transaction'}), 404

    if donation.status == 'completed':
        return jsonify({'success': True, 'message': 'Already verified'}), 200

    payload, paystack_data = _verify_with_paystack(reference)
    if payload is None:
        return jsonify({'success': False, 'message': 'Payments are not configured or unreachable'}), 502

    expected_kobo = _expected_kobo(donation)
    charge_status = paystack_data.get('status')

    if payload.get('status') and charge_status == 'success' \
            and paystack_data.get('amount') == expected_kobo \
            and (paystack_data.get('currency') or '').upper() == GIVING_CURRENCY:
        _set_donation_status_once(donation.id, 'completed', from_statuses=('pending', 'failed'))
        return jsonify({'success': True, 'message': 'Payment verified'}), 200

    if payload.get('status') and charge_status in PAYSTACK_FINAL_FAILURE_STATUSES:
        # Definitive failure from Paystack. Only downgrade from 'pending' —
        # never stomp a 'completed' a concurrent webhook may have just set.
        _set_donation_status_once(donation.id, 'failed')
        return jsonify({'success': False, 'message': 'Payment was not successful'}), 400

    if payload.get('status') and charge_status == 'success':
        # Paid, but not the amount/currency we asked for — don't complete,
        # leave pending for manual review rather than marking failed.
        current_app.logger.warning(
            f'paystack_verify: reference={reference!r} amount/currency mismatch '
            f'(got {paystack_data.get("amount")!r} {paystack_data.get("currency")!r}, expected {expected_kobo} {GIVING_CURRENCY})'
        )
        return jsonify({'success': False, 'message': 'Payment could not be verified'}), 400

    # Still processing, or a transient Paystack/API error: leave 'pending'
    # (the webhook will reconcile it) and let the client retry later.
    return jsonify({'success': False, 'pending': True,
                    'message': 'Payment is still being confirmed. You will see it shortly.'}), 202


@api_bp.route('/paystack/webhook', methods=['POST'])
@csrf.exempt
@limiter.exempt
def paystack_webhook():
    """
    Server-to-server webhook — the authoritative source of truth for
    payment status, independent of whether the donor's browser ever calls
    /api/paystack/verify. Paystack requires a fast 200 response and retries
    on failure/timeout, so this stays deliberately lightweight.

    Trust model: there's no session/CSRF token on a server-to-server call,
    so the X-Paystack-Signature header (HMAC-SHA512 of the raw body, keyed
    with the secret key) is what proves this request actually came from
    Paystack — verified before any of the payload is trusted.
    """
    secret_key = current_app.config.get('PAYSTACK_SECRET_KEY', '')
    signature = request.headers.get('X-Paystack-Signature', '')
    raw_body = request.get_data()

    if not secret_key or not signature:
        current_app.logger.warning('paystack_webhook: missing secret key or signature header')
        return jsonify({'success': False}), 401

    expected_signature = hmac.new(secret_key.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        current_app.logger.warning('paystack_webhook: signature mismatch, rejecting')
        return jsonify({'success': False}), 401

    event = request.get_json(silent=True) or {}
    event_type = event.get('event')
    data = event.get('data', {})
    reference = data.get('reference')

    current_app.logger.info(f'paystack_webhook: received {event_type!r} for reference={reference!r}')

    if event_type != 'charge.success' or not reference:
        # Not an event this app acts on (or malformed) — 200 so Paystack
        # doesn't keep retrying something we're intentionally ignoring.
        return jsonify({'success': True}), 200

    donation = Giving.query.filter_by(paystack_reference=reference).first()
    if not donation:
        current_app.logger.warning(f'paystack_webhook: no donation found for reference={reference!r}')
        return jsonify({'success': True}), 200

    expected_kobo = _expected_kobo(donation)
    if data.get('status') == 'success' and data.get('amount') == expected_kobo \
            and (data.get('currency') or '').upper() == GIVING_CURRENCY:
        # A verify call may have marked it 'failed' on an earlier definitive
        # status; Paystack's signed charge.success is authoritative.
        changed = _set_donation_status_once(donation.id, 'completed', from_statuses=('pending', 'failed'))
        if changed:
            current_app.logger.info(f'paystack_webhook: donation {donation.id} marked completed')
    else:
        current_app.logger.warning(
            f'paystack_webhook: reference={reference!r} status/amount/currency mismatch, not completing'
        )

    return jsonify({'success': True}), 200


# Member testimony submission routes register onto main_bp.
from app import testimony_submit  # noqa: E402,F401
