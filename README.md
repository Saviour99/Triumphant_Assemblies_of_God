A website for Triumphant Assemblies of God
# Triumphant Assemblies of God (TAG) - Church Website

A professional, responsive church website built with **Flask**, **MySQL**, **Bootstrap 5**, and **Vanilla JavaScript**. Designed specifically for **Triumphant Assemblies of God** with a Ghanaian/West African cultural identity.

## 🌟 Features

### Core Pages
- **Home** - Hero section with animated elements, church stats, upcoming events, sermons preview
- **About** - Church history, vision, mission, core values, and leadership team bios
- **Ministries** - Detailed descriptions of 6 active ministries with volunteer opportunities
- **Sermons** - Video and audio archives with search and filter functionality
- **Events** - Church calendar, upcoming events, and special programs
- **Blog** - Articles, devotionals, testimonies, and pastor's messages
- **Contact** - Contact form, prayer requests, giving portal, and location map

### Interactive Features
- 🎨 **Animated Preloader** - Golden cross animation on page load
- 📊 **Animated Counters** - Church statistics with smooth counting animations
- 🎬 **Smooth Scroll Animations** - Intersection Observer API for reveal effects
- 🎪 **Responsive Carousels** - Event and testimony sliders
- 📱 **Mobile-First Design** - Fully responsive on all devices
- 💬 **WhatsApp Integration** - Floating chat button for quick contact
- 🔝 **Back-to-Top Button** - Fixed button for easy navigation
- 📧 **Newsletter Signup** - Subscribe to church updates
- 💰 **Online Giving Portal** - Secure giving with multiple options

### Design System
- **Color Palette**: Gold (#C8973A), Royal Blue (#0D2B6B), White
- **Typography**: Cormorant Garamond (headings), Nunito (body)
- **Gradients**: Rich gold-to-blue gradients throughout
- **Icons**: Font Awesome 6.4.0
- **Framework**: Bootstrap 5.3.0

### Security Features
- ✅ Input sanitization on all forms
- ✅ CSRF protection ready
- ✅ Email validation
- ✅ Content Security Policy meta tags
- ✅ No inline event handlers
- ✅ External links with `noopener noreferrer`

## 📋 Requirements

- Python 3.8+
- MySQL 5.7+
- pip (Python package manager)

## 🚀 Installation & Setup

### 1. Clone or Download the Project
```bash
cd /home/ubuntu/tag_church_flask
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
```bash
cp .env.example .env
```

Edit `.env` with your MySQL credentials:
```
FLASK_ENV=development
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=tag_church
```

### 5. Initialize Database
```bash
python init_db.py
```

This will create the database and all necessary tables:
- `prayer_requests` - Prayer request submissions
- `contact_messages` - Contact form submissions
- `newsletter_subscribers` - Newsletter subscribers
- `giving` - Online giving records
- `sermons` - Sermon archive
- `events` - Church events
- `blog_posts` - Blog articles
- `testimonies` - Member testimonies

### 6. Run the Application
```bash
python run.py
```

The website will be available at `http://localhost:5000`

## 📁 Project Structure

```
tag_church_flask/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── routes.py             # All routes and API endpoints
│   ├── templates/            # Jinja2 HTML templates
│   │   ├── base.html         # Base template with nav and footer
│   │   ├── index.html        # Home page
│   │   ├── about.html        # About page
│   │   ├── ministries.html   # Ministries page
│   │   ├── sermons.html      # Sermons page
│   │   ├── events.html       # Events page
│   │   ├── blog.html         # Blog page
│   │   └── contact.html      # Contact page
│   └── static/
│       ├── css/
│       │   └── style.css     # Main stylesheet
│       ├── js/
│       │   └── main.js       # JavaScript functionality
│       └── images/           # Image assets
├── config.py                 # Flask configuration
├── run.py                    # Application entry point
├── init_db.py                # Database initialization
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
└── README.md                 # This file
```

## 🔧 Configuration

### Database Setup
The application uses MySQL with the following structure:

**Connection String Format:**
```
mysql://[user]:[password]@[host]/[database]
```

**Tables Created:**
- `prayer_requests` - Stores prayer request submissions
- `contact_messages` - Stores contact form messages
- `newsletter_subscribers` - Email list for newsletter
- `giving` - Records of online giving
- `sermons` - Sermon archive (for future expansion)
- `events` - Church events (for future expansion)
- `blog_posts` - Blog articles (for future expansion)
- `testimonies` - Member testimonies (for future expansion)

### Environment Variables
```
FLASK_ENV          # development or production
FLASK_APP          # run.py
SECRET_KEY         # Secret key for session management
MYSQL_HOST         # Database host
MYSQL_USER         # Database username
MYSQL_PASSWORD     # Database password
MYSQL_DB           # Database name
```

## 📧 API Endpoints

### Prayer Request
**POST** `/api/prayer-request`
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "topic": "Healing",
  "message": "Please pray for my mother's recovery"
}
```

### Contact Form
**POST** `/api/contact-form`
```json
{
  "name": "Jane Smith",
  "email": "jane@example.com",
  "subject": "Website Inquiry",
  "message": "I have a question about..."
}
```

### Newsletter Signup
**POST** `/api/newsletter`
```json
{
  "email": "subscriber@example.com"
}
```

### Online Giving
**POST** `/api/giving`
```json
{
  "amount": 100.00,
  "giving_type": "tithe",
  "donor_name": "John Donor",
  "donor_email": "donor@example.com"
}
```

## 🎨 Customization

### Colors
Edit the CSS variables in `app/static/css/style.css`:
```css
:root {
    --gold: #C8973A;
    --blue: #0D2B6B;
    --white: #FFFFFF;
    /* ... other variables */
}
```

### Church Information
Update church details in `app/routes.py`:
```python
CHURCH_INFO = {
    'name': 'Triumphant Assemblies of God (TAG)',
    'address': 'Your address here',
    'email': 'your-email@example.com',
    'phone': 'Your phone number',
    # ... other info
}
```

### Leadership
Add or update leadership bios in `app/routes.py`:
```python
LEADERSHIP = [
    {
        'name': 'Leader Name',
        'title': 'Position',
        'bio': 'Biography...',
        'image': 'image.jpg'
    },
    # ... more leaders
]
```

## 🚀 Deployment

### Using Gunicorn (Production)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 run:app
```

### Using Docker (Optional)
Create a `Dockerfile`:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "run:app"]
```

Build and run:
```bash
docker build -t tag-church .
docker run -p 5000:5000 tag-church
```

### Cloud Deployment
The application can be deployed to:
- **Heroku** - Easy deployment with `Procfile`
- **AWS** - EC2 or Elastic Beanstalk
- **Google Cloud** - App Engine or Cloud Run
- **DigitalOcean** - App Platform or Droplets
- **PythonAnywhere** - Python hosting platform

## 📱 Responsive Design

The website is fully responsive and tested on:
- ✅ Mobile (320px - 480px)
- ✅ Tablet (481px - 768px)
- ✅ Desktop (769px - 1024px)
- ✅ Large Desktop (1025px+)

## 🔒 Security Best Practices

1. **Input Validation** - All form inputs are validated and sanitized
2. **CSRF Protection** - Ready for Flask-WTF integration
3. **SQL Injection Prevention** - Using parameterized queries
4. **XSS Protection** - HTML escaping in templates
5. **HTTPS** - Recommended for production
6. **Environment Variables** - Sensitive data in `.env` file
7. **Secure Headers** - Content Security Policy meta tags

## 🐛 Troubleshooting

### Database Connection Error
- Ensure MySQL is running
- Check credentials in `.env`
- Verify database name exists

### Static Files Not Loading
- Run `python init_db.py` to initialize database
- Check file paths in templates
- Ensure `static/` folder exists

### Forms Not Submitting
- Check browser console for JavaScript errors
- Verify API endpoints are correct
- Ensure database tables exist

## 📞 Support & Contact

For issues or questions:
- **Email**: {{ church_info.email }}
- **Phone**: {{ church_info.phone }}
- **Address**: {{ church_info.address }}

## 📄 License

This project is proprietary to Triumphant Assemblies of God (TAG).

## 🙏 Acknowledgments

- Bootstrap 5 for responsive framework
- Font Awesome for icons
- Google Fonts for typography
- Unsplash for placeholder images
- Three.js for 3D capabilities

---

**Built with ❤️ for Triumphant Assemblies of God (TAG)**

*A Place of Triumph, Love & Purpose*


live

Jump to live
