# TAG Church Website - Quick Start Guide

Fast setup guide to get the website running in 5 minutes.

## ⚡ 5-Minute Setup

### Step 1: Install Dependencies (1 minute)
```bash
cd /home/ubuntu/tag_church_flask
pip install -r requirements.txt
```

### Step 2: Configure Database (1 minute)
```bash
cp .env.example .env
# Edit .env with your MySQL credentials
nano .env
```

Example `.env`:
```
FLASK_ENV=development
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=tag_church
SECRET_KEY=your-secret-key-here
```

### Step 3: Initialize Database (1 minute)
```bash
python init_db.py
```

### Step 4: Run Application (1 minute)
```bash
python run.py
```

### Step 5: Access Website (1 minute)
Open your browser and go to:
```
http://localhost:5000
```

## 📋 What You Get

✅ **7 Complete Pages**
- Home (with animations and hero section)
- About (with leadership bios)
- Ministries (with 8 ministry descriptions)
- Sermons (with video/audio archives)
- Events (with calendar and listings)
- Blog (with articles and testimonies)
- Contact (with forms and map)

✅ **Interactive Features**
- Prayer request form
- Contact form
- Newsletter signup
- Online giving portal
- WhatsApp chat button
- Back-to-top button
- Animated counters
- Scroll reveal animations

✅ **Professional Design**
- Responsive on all devices
- Gold & Blue color scheme
- Smooth animations
- Fast loading
- Secure forms

## 🔧 Troubleshooting

### MySQL Connection Error
```bash
# Make sure MySQL is running
sudo service mysql start

# Or check if MySQL is installed
mysql --version
```

### Port Already in Use
```bash
# Change port in run.py
# Or kill existing process
lsof -i :5000
kill -9 <PID>
```

### Module Not Found
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

## 📚 Next Steps

1. **Customize Content**
   - Edit church info in `app/routes.py`
   - Update images in templates
   - Modify text and descriptions

2. **Add More Features**
   - Add email notifications
   - Integrate payment gateway
   - Add live stream
   - Add member portal

3. **Deploy to Production**
   - See `DEPLOYMENT_GUIDE.md`
   - Choose hosting provider
   - Configure domain
   - Setup SSL certificate

## 📖 Documentation

- **Full Setup**: See `README.md`
- **Deployment**: See `DEPLOYMENT_GUIDE.md`
- **Performance**: See `PERFORMANCE_GUIDE.md`
- **API Endpoints**: See `README.md` (API Endpoints section)

## 🎯 Common Tasks

### Change Church Information
Edit `app/routes.py`:
```python
CHURCH_INFO = {
    'name': 'Your Church Name',
    'address': 'Your Address',
    'email': 'your-email@example.com',
    'phone': '+233 XXX XXX XXXX',
    # ... more info
}
```

### Change Colors
Edit `app/static/css/style.css`:
```css
:root {
    --gold: #C8973A;
    --blue: #0D2B6B;
    --white: #FFFFFF;
}
```

### Add New Page
1. Create `app/templates/newpage.html`
2. Add route in `app/routes.py`
3. Update navigation in `base.html`

### Update Leadership
Edit `app/routes.py`:
```python
LEADERSHIP = [
    {
        'name': 'Rev. Rexford Peprah',
        'title': 'Senior Pastor',
        'bio': 'Biography here...',
        'image': 'image.jpg'
    },
    # Add more leaders
]
```

## 💡 Tips

- **Backup Database**: `mysqldump -u root -p tag_church > backup.sql`
- **View Logs**: Check `logs/tag_church.log` for errors
- **Test Forms**: Submit test data to verify database connection
- **Check Performance**: Use Google PageSpeed Insights
- **Monitor Traffic**: Enable Google Analytics

## 🚀 Ready to Deploy?

When you're ready to go live:
1. Read `DEPLOYMENT_GUIDE.md`
2. Choose a hosting provider
3. Follow the deployment steps
4. Configure your domain
5. Setup SSL certificate
6. Monitor performance

## 📞 Support

- **Documentation**: See README.md
- **Issues**: Check logs in `logs/` directory
- **Performance**: See PERFORMANCE_GUIDE.md
- **Deployment**: See DEPLOYMENT_GUIDE.md

---

**Version**: 1.0.0
**Status**: Production Ready ✅
**Last Updated**: May 2024