import uuid

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, Response
from app import db
from app.models import (
    PrayerRequest, ContactMessage, NewsletterSubscriber, Giving,
    VideoSermon, AudioSermon, Devotion, Ebook, Testimony
)
from datetime import datetime, date
import re

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

# Church data (can be moved to database later)
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
    return render_template('public/index.html', church_info=CHURCH_INFO)

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
                         church_info=CHURCH_INFO)

@main_bp.route('/ministries')
def ministries():
    """Ministries page"""
    return render_template('public/ministries.html', ministries=MINISTRIES, church_info=CHURCH_INFO)

@main_bp.route('/sermons')
def sermons():
    """Sermons page"""
    video_sermons = VideoSermon.query.order_by(VideoSermon.sermon_date.desc()).all()
    audio_sermons = AudioSermon.query.order_by(AudioSermon.sermon_date.desc()).all()
    return render_template(
        'public/sermons.html',
        video_sermons=video_sermons,
        audio_sermons=audio_sermons,
        church_info=CHURCH_INFO
    )

@main_bp.route('/events')
def events():
    """Events page"""
    return render_template('public/events.html', church_info=CHURCH_INFO)

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
    recent_testimonies = Testimony.query.order_by(Testimony.created_at.desc()).limit(3).all()

    return render_template(
        'public/blog.html',
        devotion=devotion,
        past_devotions=past_devotions,
        recent_testimonies=recent_testimonies,
        church_info=CHURCH_INFO
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
        church_info=CHURCH_INFO
    )


@main_bp.route('/blog/worship')
def blog_worship():
    """Worship reading list."""
    ebooks = Ebook.query.filter_by(category='worship').order_by(Ebook.title.asc()).all()
    return render_template('public/blog_ebooks.html', ebooks=ebooks, category='worship', church_info=CHURCH_INFO)


@main_bp.route('/blog/leadership')
def blog_leadership():
    """Leadership reading list."""
    ebooks = Ebook.query.filter_by(category='leadership').order_by(Ebook.title.asc()).all()
    return render_template('public/blog_ebooks.html', ebooks=ebooks, category='leadership', church_info=CHURCH_INFO)


@main_bp.route('/blog/testimonies')
def blog_testimonies():
    """Member testimonies."""
    testimonies = Testimony.query.order_by(Testimony.created_at.desc()).all()
    return render_template('public/blog_testimonies.html', testimonies=testimonies, church_info=CHURCH_INFO)


@main_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('public/contact.html', church_info=CHURCH_INFO)

@main_bp.route('/giving')
def giving():
    """Offering page"""
    return render_template('public/offering.html', church_info=CHURCH_INFO)


@main_bp.route('/robots.txt')
def robots_txt():
    """Allow public pages, keep auth/dashboard areas out of the crawl."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /members/",
        f"Sitemap: {request.url_root}sitemap.xml",
    ]
    return Response("\n".join(lines) + "\n", mimetype='text/plain')


@main_bp.route('/sitemap.xml')
def sitemap_xml():
    """Dynamically generated — built from request.url_root so it's correct
    on localhost today and on whatever domain the site is deployed to."""
    base = request.url_root.rstrip('/')
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

from app.utils import validate_email, sanitize_text as sanitize_input

@api_bp.route('/prayer-request', methods=['POST'])
def prayer_request():
    """Handle prayer request submissions"""
    try:
        data = request.get_json()

        name = sanitize_input(data.get('name', ''))
        email = sanitize_input(data.get('email', ''))
        topic = sanitize_input(data.get('topic', ''))
        message = sanitize_input(data.get('message', ''))

        if not all([name, email, topic, message]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400

        if len(message) < 10:
            return jsonify({'success': False, 'message': 'Message must be at least 10 characters'}), 400

        db.session.add(PrayerRequest(name=name, email=email, topic=topic, message=message))
        db.session.commit()

        return jsonify({'success': True, 'message': 'Prayer request submitted successfully'}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'prayer_request error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


@api_bp.route('/contact-form', methods=['POST'])
def contact_form():
    """Handle contact form submissions"""
    try:
        data = request.get_json()

        name = sanitize_input(data.get('name', ''))
        email = sanitize_input(data.get('email', ''))
        subject = sanitize_input(data.get('subject', ''))
        message = sanitize_input(data.get('message', ''))

        if not all([name, email, subject, message]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400

        db.session.add(ContactMessage(name=name, email=email, subject=subject, message=message))
        db.session.commit()

        return jsonify({'success': True, 'message': 'Message sent successfully'}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'contact_form error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


@api_bp.route('/newsletter', methods=['POST'])
def newsletter():
    """Handle newsletter signup"""
    try:
        data = request.get_json()
        email = sanitize_input(data.get('email', ''))

        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400

        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400

        if NewsletterSubscriber.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email already subscribed'}), 400

        db.session.add(NewsletterSubscriber(email=email))
        db.session.commit()

        return jsonify({'success': True, 'message': 'Successfully subscribed to newsletter'}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'newsletter error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


# ============ GIVING / PAYSTACK ============

VALID_GIVING_TYPES = {'tithe', 'offering', 'missions', 'building_fund', 'other'}


@api_bp.route('/giving/init', methods=['POST'])
def giving_init():
    """
    Step 1 of the Paystack flow: create a pending Giving row server-side
    (never trusting a client-supplied 'amount already paid' claim) and hand
    back a reference for the browser to open the Paystack popup with.
    """
    try:
        data = request.get_json()

        giving_type = sanitize_input(data.get('giving_type', ''))
        donor_name = sanitize_input(data.get('donor_name', ''))
        donor_email = sanitize_input(data.get('donor_email', ''))

        if giving_type not in VALID_GIVING_TYPES:
            return jsonify({'success': False, 'message': 'Invalid giving type'}), 400

        if not all([donor_name, donor_email]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if not validate_email(donor_email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400

        try:
            amount = float(data.get('amount'))
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid amount'}), 400

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
            'amount': amount,
            'email': donor_email,
            'public_key': current_app.config.get('PAYSTACK_PUBLIC_KEY', '')
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'giving_init error: {e}')
        return jsonify({'success': False, 'message': 'Something went wrong. Please try again.'}), 500


@api_bp.route('/paystack/verify', methods=['POST'])
def paystack_verify():
    """
    Step 2: verify the transaction server-side against Paystack's API before
    ever marking a donation completed. The browser's callback is never trusted
    on its own.
    """
    import requests

    reference = sanitize_input((request.get_json() or {}).get('reference', ''))
    if not reference:
        return jsonify({'success': False, 'message': 'Missing reference'}), 400

    donation = Giving.query.filter_by(paystack_reference=reference).first()
    if not donation:
        return jsonify({'success': False, 'message': 'Unknown transaction'}), 404

    if donation.status == 'completed':
        return jsonify({'success': True, 'message': 'Already verified'}), 200

    secret_key = current_app.config.get('PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        current_app.logger.error('PAYSTACK_SECRET_KEY is not configured')
        return jsonify({'success': False, 'message': 'Payments are not configured'}), 503

    try:
        resp = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers={'Authorization': f'Bearer {secret_key}'},
            timeout=10
        )
        payload = resp.json()
    except Exception as e:
        current_app.logger.error(f'paystack_verify request error: {e}')
        return jsonify({'success': False, 'message': 'Could not reach Paystack'}), 502

    paystack_data = payload.get('data', {})
    expected_kobo = round(float(donation.amount) * 100)

    if payload.get('status') and paystack_data.get('status') == 'success' \
            and paystack_data.get('amount') == expected_kobo:
        donation.status = 'completed'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Payment verified'}), 200

    donation.status = 'failed'
    db.session.commit()
    return jsonify({'success': False, 'message': 'Payment could not be verified'}), 400