from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from app import db
from datetime import datetime
import re

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

# Church data (can be moved to database later)
CHURCH_INFO = {
    'name': 'Triumphant Assemblies of God (TAG)',
    'address': 'Post Office Box AN 6130, Accra North, Ghana, West Africa',
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
    return render_template('public/sermons.html', church_info=CHURCH_INFO)

@main_bp.route('/events')
def events():
    """Events page"""
    return render_template('public/events.html', church_info=CHURCH_INFO)

@main_bp.route('/blog')
def blog():
    """Blog page"""
    return render_template('public/blog.html', church_info=CHURCH_INFO)

@main_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('public/contact.html', church_info=CHURCH_INFO)

@main_bp.route('/giving')
def giving():
    """Offering page"""
    return render_template('public/offering.html', church_info=CHURCH_INFO)

# ============ API ROUTES ============

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def sanitize_input(text):
    """Basic input sanitization"""
    if not text:
        return ''
    # Remove potentially dangerous characters
    text = text.strip()
    text = re.sub(r'[<>\"\'%;()&+]', '', text)
    return text

@api_bp.route('/prayer-request', methods=['POST'])
def prayer_request():
    """Handle prayer request submissions"""
    try:
        data = request.get_json()
        
        # Validate inputs
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
        
        # Insert into database
        cur = db.connection.cursor()
        cur.execute("""
            INSERT INTO prayer_requests (name, email, topic, message, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, email, topic, message, datetime.now()))
        db.connection.commit()
        cur.close()
        
        return jsonify({'success': True, 'message': 'Prayer request submitted successfully'}), 201
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/contact-form', methods=['POST'])
def contact_form():
    """Handle contact form submissions"""
    try:
        data = request.get_json()
        
        # Validate inputs
        name = sanitize_input(data.get('name', ''))
        email = sanitize_input(data.get('email', ''))
        subject = sanitize_input(data.get('subject', ''))
        message = sanitize_input(data.get('message', ''))
        
        if not all([name, email, subject, message]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        
        # Insert into database
        cur = db.connection.cursor()
        cur.execute("""
            INSERT INTO contact_messages (name, email, subject, message, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, email, subject, message, datetime.now()))
        db.connection.commit()
        cur.close()
        
        return jsonify({'success': True, 'message': 'Message sent successfully'}), 201
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

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
        
        # Check if already subscribed
        cur = db.connection.cursor()
        cur.execute("SELECT id FROM newsletter_subscribers WHERE email = %s", (email,))
        existing = cur.fetchone()
        
        if existing:
            cur.close()
            return jsonify({'success': False, 'message': 'Email already subscribed'}), 400
        
        # Insert new subscriber
        cur.execute("""
            INSERT INTO newsletter_subscribers (email, subscribed_at)
            VALUES (%s, %s)
        """, (email, datetime.now()))
        db.connection.commit()
        cur.close()
        
        return jsonify({'success': True, 'message': 'Successfully subscribed to newsletter'}), 201
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/giving', methods=['POST'])
def giving():
    """Handle online giving submissions"""
    try:
        data = request.get_json()
        
        # Validate inputs
        amount = data.get('amount')
        giving_type = sanitize_input(data.get('giving_type', ''))
        donor_name = sanitize_input(data.get('donor_name', ''))
        donor_email = sanitize_input(data.get('donor_email', ''))
        
        if not all([amount, giving_type, donor_name, donor_email]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid amount'}), 400
        
        if not validate_email(donor_email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        
        # Insert into database
        cur = db.connection.cursor()
        cur.execute("""
            INSERT INTO giving (amount, giving_type, donor_name, donor_email, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (amount, giving_type, donor_name, donor_email, datetime.now()))
        db.connection.commit()
        cur.close()
        
        return jsonify({'success': True, 'message': 'Giving recorded successfully'}), 201
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500