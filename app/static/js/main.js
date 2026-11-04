/* ============================================
   TAG CHURCH WEBSITE - MAIN JAVASCRIPT
   ============================================ */

// ============ MOTION PREFERENCES ============
const prefersReducedMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const prefersSaveData = !!(navigator.connection && navigator.connection.saveData);

// (Preloader lives in js/preloader.js, loaded in <head>.)

// ============ HERO BACKGROUND VIDEO ============
// The <video> ships without a src (preload="none" + data-src) so visitors who
// asked for reduced motion or reduced data only ever download the poster.
(function() {
    const video = document.getElementById('heroVideo');
    if (!video) return;
    if (prefersReducedMotion || prefersSaveData || !video.dataset.src) return;

    const toggle = document.getElementById('heroVideoToggle');
    const hero = document.getElementById('hero');

    video.src = video.dataset.src;
    video.muted = true;
    video.addEventListener('playing', () => hero && hero.classList.add('video-ready'), { once: true });
    const attempt = video.play();
    if (attempt && attempt.catch) attempt.catch(() => { /* autoplay blocked: poster stays */ });

    if (toggle) {
        toggle.hidden = false;
        toggle.addEventListener('click', function() {
            const icon = this.querySelector('i');
            if (video.paused) {
                video.play();
                this.setAttribute('aria-pressed', 'false');
                this.setAttribute('aria-label', 'Pause background video');
                if (icon) icon.className = 'fa-solid fa-pause';
            } else {
                video.pause();
                this.setAttribute('aria-pressed', 'true');
                this.setAttribute('aria-label', 'Play background video');
                if (icon) icon.className = 'fa-solid fa-play';
            }
        });
    }

    // Don't spend battery decoding video the visitor has scrolled past.
    if ('IntersectionObserver' in window && hero) {
        new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (toggle && toggle.getAttribute('aria-pressed') === 'true') return;
                if (entry.isIntersecting) { video.play().catch(() => {}); } else { video.pause(); }
            });
        }, { threshold: 0.1 }).observe(hero);
    }
})();

// ============ NAVBAR SCROLL EFFECT (FIXED FOR ALL PAGES) ============
const navbar = document.getElementById('navbar');
let lastScrollTop = 0;

// Function to update navbar state based on scroll
function updateNavbarState() {
    let scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    
    if (scrollTop > 100) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
    
    lastScrollTop = scrollTop <= 0 ? 0 : scrollTop;
}

// Call on page load to set initial state
updateNavbarState();

// Call on scroll
window.addEventListener('scroll', updateNavbarState);

// Call when page becomes visible (tab switching)
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        updateNavbarState();
    }
});

// ============ BACK TO TOP BUTTON ============
const backToTopBtn = document.getElementById('backToTop');

if (backToTopBtn) {
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
}

// ============ COOKIE CONSENT BANNER ============
(function() {
    const CONSENT_KEY = 'tag_cookie_consent';
    const banner = document.getElementById('cookieConsent');
    const acceptBtn = document.getElementById('cookieConsentAccept');

    if (!banner || !acceptBtn) {
        return;
    }

    let alreadyAccepted = false;
    try {
        alreadyAccepted = localStorage.getItem(CONSENT_KEY) === 'accepted';
    } catch (e) {
        // localStorage unavailable (e.g. private browsing) - fall back to
        // showing the banner every visit rather than breaking the page.
    }

    if (!alreadyAccepted) {
        setTimeout(() => banner.classList.add('show'), 800);
    }

    acceptBtn.addEventListener('click', function() {
        try {
            localStorage.setItem(CONSENT_KEY, 'accepted');
        } catch (e) {
            // Ignore storage failures - the banner will just reappear next visit.
        }
        banner.classList.remove('show');
    });
})();

// (The old per-section fade-in on scroll was removed in the 2026 layout
// refresh: the hero carries the page's one orchestrated entrance.)

// ============ ANIMATED COUNTERS ============
function animateCounter(element, target, duration = 2000) {
    if (prefersReducedMotion) {
        element.textContent = target.toLocaleString();
        return;
    }
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
function initializeCounters() {
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
}

// Initialize on DOM ready and page load
document.addEventListener('DOMContentLoaded', initializeCounters);
window.addEventListener('load', initializeCounters);

// ============ SERMON SEARCH & PAGINATION (FIXED) ============
function initializeSermonSearch() {
    const SERMONS_PER_PAGE = 4;
    let currentPage = 1;
    let filteredSermons = [];

    const allSermons = document.querySelectorAll('.col-lg-6.mb-4');
    const sermonSearch = document.getElementById('sermonSearch');
    const pagination = document.querySelector('.pagination');

    if (!allSermons.length || !sermonSearch || !pagination) {
        return; // Exit if sermon elements don't exist
    }

    function getSermonText(sermon) {
        const title = sermon.querySelector('.sermon-title')?.textContent.toLowerCase() || '';
        const speaker = sermon.querySelector('.sermon-speaker')?.textContent.toLowerCase() || '';
        const description = sermon.querySelector('.sermon-description')?.textContent.toLowerCase() || '';
        const date = sermon.querySelector('.sermon-date')?.textContent.toLowerCase() || '';
        return `${title} ${speaker} ${description} ${date}`;
    }

    function renderSermons() {
        const start = (currentPage - 1) * SERMONS_PER_PAGE;
        const end = start + SERMONS_PER_PAGE;

        allSermons.forEach(sermon => sermon.style.display = 'none');

        filteredSermons.slice(start, end).forEach(sermon => {
            sermon.style.display = 'block';
        });

        renderPagination();
    }

    function renderPagination() {
        const totalPages = Math.ceil(filteredSermons.length / SERMONS_PER_PAGE);

        pagination.innerHTML = '';

        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="javascript:void(0);">Previous</a>`;
        prevLi.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (currentPage > 1) { 
                currentPage--; 
                renderSermons();
            }
        });
        pagination.appendChild(prevLi);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === currentPage ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="javascript:void(0);">${i}</a>`;
            li.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                currentPage = i;
                renderSermons();
            });
            pagination.appendChild(li);
        }

        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentPage === totalPages || totalPages === 0 ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="javascript:void(0);">Next</a>`;
        nextLi.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (currentPage < totalPages) { 
                currentPage++; 
                renderSermons();
            }
        });
        pagination.appendChild(nextLi);
    }

    function filterSermons(query) {
        currentPage = 1;
        if (!query.trim()) {
            filteredSermons = [...allSermons];
        } else {
            filteredSermons = [...allSermons].filter(sermon =>
                getSermonText(sermon).includes(query.toLowerCase())
            );
        }
        renderSermons();
        checkEmpty();
    }

    // No results message
    function checkEmpty() {
        const sermonRow = document.querySelector('.sermons-section .row:last-of-type');
        if (!sermonRow) return;
        
        let noResults = document.getElementById('no-results');

        if (filteredSermons.length === 0) {
            if (!noResults) {
                noResults = document.createElement('p');
                noResults.id = 'no-results';
                noResults.className = 'text-center text-muted mt-4';
                noResults.textContent = 'No sermons found matching your search.';
                sermonRow.after(noResults);
            }
        } else {
            if (noResults) noResults.remove();
        }
    }

    // Init
    if (allSermons.length > 0) {
        filteredSermons = [...allSermons];
        renderSermons();
    }

    // Search listener with debounce
    let searchTimeout;
    sermonSearch.addEventListener('input', function () {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            filterSermons(this.value);
        }, 300);
    });
}

// Initialize sermon search on DOM ready and page load
document.addEventListener('DOMContentLoaded', initializeSermonSearch);
window.addEventListener('load', initializeSermonSearch);

// ============ FORM HANDLING ============

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

// Prayer Request Form
function initializePrayerForm() {
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
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
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
}

// Contact Form
function initializeContactForm() {
    const contactForm = document.getElementById('contactForm');
    if (contactForm) {
        contactForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = {
                name: document.getElementById('contactName').value,
                email: document.getElementById('contactEmail').value,
                phone: document.getElementById('contactPhone').value,
                subject: document.getElementById('contactSubject').value,
                message: document.getElementById('contactMessage').value
            };
            
            try {
                const response = await fetch('/api/contact-form', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
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
}

// Newsletter Forms (blog sidebar + footer both post to the same JSON API)
function initializeNewsletterForm(formId, emailFieldId) {
    const newsletterForm = document.getElementById(formId);
    if (newsletterForm) {
        newsletterForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const email = document.getElementById(emailFieldId).value;

            try {
                const response = await fetch('/api/newsletter', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
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
}

// ============ ONLINE GIVING (Paystack) ============
// Moved here from an inline <script> in offering.html so the CSP can drop
// 'unsafe-inline'. The public key and receipt URL come from data attributes
// on #givingForm. Flow: /api/giving/init -> Paystack popup -> /api/paystack/verify
// -> redirect to the receipt page, which reads the real status server-side.
function initializeGivingForm() {
    const form = document.getElementById('givingForm');
    if (!form) return;

    const amountInput = document.getElementById('givingAmount');
    document.querySelectorAll('.quick-amount-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            amountInput.value = this.dataset.amount;
            amountInput.focus();
        });
    });

    const publicKey = form.dataset.paystackKey || '';
    const thankYouUrl = form.dataset.thankYouUrl || '';
    const csrfToken = getCsrfToken();

    function showGivingAlert(message, type) {
        const box = document.getElementById('givingAlert');
        box.innerHTML = '';
        const div = document.createElement('div');
        div.className = `alert alert-${type}`;
        div.setAttribute('role', 'alert');
        div.textContent = message;
        box.appendChild(div);
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        if (!publicKey || typeof PaystackPop === 'undefined') {
            showGivingAlert('Online giving is temporarily unavailable. Please try again later.', 'danger');
            return;
        }

        const payload = {
            amount: amountInput.value,
            giving_type: document.getElementById('givingType').value,
            donor_name: document.getElementById('donorName').value,
            donor_email: document.getElementById('donorEmail').value
        };

        fetch('/api/giving/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(payload)
        })
            .then(res => res.json())
            .then(data => {
                if (!data.success) {
                    showGivingAlert(data.message || 'Something went wrong.', 'danger');
                    return;
                }

                const handler = PaystackPop.setup({
                    key: data.public_key,
                    email: data.email,
                    amount: Math.round(data.amount * 100),
                    currency: 'GHS',
                    ref: data.reference,
                    callback: function(response) {
                        showGivingAlert('Confirming your payment…', 'info');
                        fetch('/api/paystack/verify', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                            body: JSON.stringify({ reference: response.reference })
                        })
                            .then(res => res.json())
                            .then(result => {
                                if (result.success) {
                                    showGivingAlert('Thank you! Your giving was received successfully.', 'success');
                                    form.reset();
                                } else {
                                    showGivingAlert('We could not verify your payment. Please contact the church office.', 'warning');
                                }
                            })
                            .catch(() => { /* the receipt page shows the real status either way */ })
                            .finally(() => {
                                if (thankYouUrl) {
                                    window.location.assign(thankYouUrl + '?reference=' + encodeURIComponent(response.reference));
                                }
                            });
                    },
                    onClose: function() {
                        showGivingAlert('Payment window closed.', 'info');
                    }
                });
                handler.openIframe();
            })
            .catch(() => showGivingAlert('Something went wrong. Please try again.', 'danger'));
    });
}

// ============ CONTACT PAGE BUTTONS ============
// (moved from an inline <script> in contact.html)
function initializeContactPageButtons() {
    document.getElementById('planVisitBtn')?.addEventListener('click', () => {
        const subject = document.getElementById('contactSubject');
        if (subject) subject.value = 'visit';
        document.getElementById('map-section')?.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth' });
    });

    document.getElementById('getDirectionsBtn')?.addEventListener('click', () => {
        const destination = encodeURIComponent('Triumphant Assemblies of God Ghana, Zuman, Accra, Ghana');
        const fallbackUrl = `https://www.google.com/maps/dir/?api=1&destination=${destination}&travelmode=driving`;

        if (!navigator.geolocation) {
            window.open(fallbackUrl, '_blank');
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (position) => {
                const origin = `${position.coords.latitude},${position.coords.longitude}`;
                window.open(
                    `https://www.google.com/maps/dir/?api=1&origin=${origin}&destination=${destination}&travelmode=driving`,
                    '_blank'
                );
            },
            () => window.open(fallbackUrl, '_blank')
        );
    });
}

// ============ PROFILE AVATAR TOGGLE ============
// (moved from an inline <script> in auth/profile.html)
function initializeAvatarToggle() {
    const toggle = document.getElementById('avatarToggle');
    const form = document.getElementById('avatarUploadForm');
    if (!toggle || !form) return;
    toggle.addEventListener('click', function() {
        const isHidden = form.classList.toggle('d-none');
        this.setAttribute('aria-expanded', String(!isHidden));
    });
}

// ============ SMALL PAGE HELPERS ============
function initializePageHelpers() {
    const year = document.getElementById('footerYear');
    if (year) year.textContent = new Date().getFullYear();

    // Interior page banner: if a page's photo is missing, drop it so the
    // banner falls back to its plain blue background.
    document.querySelectorAll('.page-header-img').forEach(img => {
        const drop = () => { img.closest('.page-header')?.classList.remove('has-image'); img.remove(); };
        if (img.complete && img.naturalWidth === 0) drop();
        else img.addEventListener('error', drop);
    });
}

// Initialize all forms once on DOM ready. (Not also on window 'load' —
// each init attaches a 'submit' listener, so registering twice would
// submit every form twice.)
document.addEventListener('DOMContentLoaded', function() {
    initializePrayerForm();
    initializeContactForm();
    initializeNewsletterForm('newsletterForm', 'newsletterEmail');
    initializeNewsletterForm('footerNewsletterForm', 'footerNewsletterEmail');
    initializeGivingForm();
    initializeContactPageButtons();
    initializeAvatarToggle();
    initializePageHelpers();
});

// ============ SINGLE-TRACK AUDIO PLAYBACK ============
// Only one <audio> element (e.g. on the sermons audio archive) plays at a
// time — starting a new track pauses every other one on the page.
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('audio').forEach(audio => {
        audio.addEventListener('play', () => {
            document.querySelectorAll('audio').forEach(other => {
                if (other !== audio) other.pause();
            });
        });
    });
});

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
function initializeCarousels() {
    const carousels = document.querySelectorAll('.carousel');
    carousels.forEach(carousel => {
        try {
            const bsCarousel = new bootstrap.Carousel(carousel, {
                interval: 5000,
                wrap: true
            });
        } catch (e) {
            console.log('Carousel initialization error:', e);
        }
    });
}

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
// A link is active on an exact path match, or when the current page is a
// sub-page of it (e.g. "/blog" stays active on "/blog/worship",
// "/blog/testimonies", etc.) — except "/" (Home), which only matches itself,
// since every path technically "starts with" it.
function setActiveNavLink() {
    const currentLocation = location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');

    navLinks.forEach(link => {
        link.classList.remove('active');
        const href = link.getAttribute('href');
        if (!href) return;

        const isActive = href === '/'
            ? currentLocation === '/'
            : currentLocation === href || currentLocation.startsWith(href + '/');

        if (isActive) {
            link.classList.add('active');
        }
    });
}

setActiveNavLink();

// ============ MOBILE MENU CLOSE ============
const navbarCollapse = document.querySelector('.navbar-collapse');

// Give the (otherwise transparent-over-hero) navbar a solid background
// while the mobile menu is open.
if (navbarCollapse && navbar) {
    navbarCollapse.addEventListener('show.bs.collapse', () => navbar.classList.add('menu-open'));
    navbarCollapse.addEventListener('hidden.bs.collapse', () => navbar.classList.remove('menu-open'));
}
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

// ============ CONSOLE LOGGING ============
console.log('%cTriumphant Assemblies of God (TAG)', 'font-size: 20px; color: #C8973A; font-weight: bold;');
console.log('%cA Place of Triumph, Love & Purpose', 'font-size: 14px; color: #0D2B6B;');