/* ============================================
   TAG CHURCH WEBSITE - MAIN JAVASCRIPT
   ============================================ */

// ============ PRELOADER ============
window.addEventListener('load', function() {
    const preloader = document.getElementById('preloader');
    if (preloader) {
        setTimeout(() => {
            preloader.style.display = 'none';
        }, 2000);
    }
});

// ============ NAVBAR SCROLL EFFECT ============
const navbar = document.getElementById('navbar');
let lastScrollTop = 0;

window.addEventListener('scroll', function() {
    let scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    
    if (scrollTop > 100) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
    
    lastScrollTop = scrollTop <= 0 ? 0 : scrollTop;
});

// ============ BACK TO TOP BUTTON ============
const backToTopBtn = document.getElementById('backToTop');

window.addEventListener('scroll', function() {
    if (window.pageYOffset > 300) {
        backToTopBtn.classList.add('show');
    } else {
        backToTopBtn.classList.remove('show');
    }
});

backToTopBtn.addEventListener('click', function() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
});

// ============ SCROLL REVEAL ANIMATION ============
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('fade-in');
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

// Observe all cards and sections
document.querySelectorAll('.card, section').forEach(el => {
    observer.observe(el);
});

// ============ ANIMATED COUNTERS ============
function animateCounter(element, target, duration = 2000) {
    let current = 0;
    const increment = target / (duration / 16);
    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            element.textContent = target.toLocaleString();
            clearInterval(timer);
        } else {
            element.textContent = Math.floor(current).toLocaleString();
        }
    }, 16);
}

// Initialize counters when they come into view
const counterElements = document.querySelectorAll('[data-counter]');
if (counterElements.length > 0) {
    const counterObserver = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting && !entry.target.classList.contains('counted')) {
                const target = parseInt(entry.target.getAttribute('data-counter'));
                animateCounter(entry.target, target);
                entry.target.classList.add('counted');
            }
        });
    }, { threshold: 0.5 });
    
    counterElements.forEach(el => counterObserver.observe(el));
}

// ============ FORM HANDLING ============

// Prayer Request Form
const prayerForm = document.getElementById('prayerForm');
if (prayerForm) {
    prayerForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = {
            name: document.getElementById('prayerName').value,
            email: document.getElementById('prayerEmail').value,
            topic: document.getElementById('prayerTopic').value,
            message: document.getElementById('prayerMessage').value
        };
        
        try {
            const response = await fetch('/api/prayer-request', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showNotification('Prayer request submitted successfully!', 'success');
                prayerForm.reset();
            } else {
                showNotification(data.message || 'Error submitting prayer request', 'error');
            }
        } catch (error) {
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

// Contact Form
const contactForm = document.getElementById('contactForm');
if (contactForm) {
    contactForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = {
            name: document.getElementById('contactName').value,
            email: document.getElementById('contactEmail').value,
            subject: document.getElementById('contactSubject').value,
            message: document.getElementById('contactMessage').value
        };
        
        try {
            const response = await fetch('/api/contact-form', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showNotification('Message sent successfully!', 'success');
                contactForm.reset();
            } else {
                showNotification(data.message || 'Error sending message', 'error');
            }
        } catch (error) {
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

// Newsletter Form
const newsletterForm = document.getElementById('newsletterForm');
if (newsletterForm) {
    newsletterForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const email = document.getElementById('newsletterEmail').value;
        
        try {
            const response = await fetch('/api/newsletter', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showNotification('Successfully subscribed to newsletter!', 'success');
                newsletterForm.reset();
            } else {
                showNotification(data.message || 'Error subscribing', 'error');
            }
        } catch (error) {
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

// Giving Form
const givingForm = document.getElementById('givingForm');
if (givingForm) {
    givingForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = {
            amount: document.getElementById('givingAmount').value,
            giving_type: document.getElementById('givingType').value,
            donor_name: document.getElementById('donorName').value,
            donor_email: document.getElementById('donorEmail').value
        };
        
        try {
            const response = await fetch('/api/giving', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showNotification('Thank you for your generous giving!', 'success');
                givingForm.reset();
            } else {
                showNotification(data.message || 'Error processing giving', 'error');
            }
        } catch (error) {
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

// ============ NOTIFICATION SYSTEM ============
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.setAttribute('role', 'alert');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        animation: slideIn 0.3s ease-out;
    `;
    
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// ============ INPUT VALIDATION ============
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function sanitizeInput(input) {
    const div = document.createElement('div');
    div.textContent = input;
    return div.innerHTML;
}

// ============ CAROUSEL AUTO-PLAY ============
const carousels = document.querySelectorAll('.carousel');
carousels.forEach(carousel => {
    const bsCarousel = new bootstrap.Carousel(carousel, {
        interval: 5000,
        wrap: true
    });
});

// ============ SMOOTH SCROLL ============
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const href = this.getAttribute('href');
        if (href !== '#' && document.querySelector(href)) {
            e.preventDefault();
            const target = document.querySelector(href);
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// ============ ACTIVE NAV LINK ============
function setActiveNavLink() {
    const currentLocation = location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    
    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === currentLocation) {
            link.classList.add('active');
        }
    });
}

setActiveNavLink();

// ============ MOBILE MENU CLOSE ============
const navbarCollapse = document.querySelector('.navbar-collapse');
const navLinks = document.querySelectorAll('.navbar-nav .nav-link');

navLinks.forEach(link => {
    link.addEventListener('click', () => {
        if (navbarCollapse.classList.contains('show')) {
            const bsCollapse = new bootstrap.Collapse(navbarCollapse, {
                toggle: false
            });
            bsCollapse.hide();
        }
    });
});

// ============ LAZY LOADING IMAGES ============
if ('IntersectionObserver' in window) {
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.remove('lazy');
                imageObserver.unobserve(img);
            }
        });
    });
    
    document.querySelectorAll('img.lazy').forEach(img => imageObserver.observe(img));
}

// ============ PULSING BUTTON EFFECT ============
const ctaButtons = document.querySelectorAll('.btn-primary-hero, .btn-gold');
ctaButtons.forEach(btn => {
    btn.addEventListener('mouseenter', function() {
        this.style.animation = 'pulse 0.6s ease-out';
    });
});

// ============ CONSOLE LOGGING ============
console.log('%cTriumphant Assemblies of God (TAG)', 'font-size: 20px; color: #C8973A; font-weight: bold;');
console.log('%cA Place of Triumph, Love & Purpose', 'font-size: 14px; color: #0D2B6B;');