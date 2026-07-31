// Admin dashboard JS: delete confirmations, stat count-up, dashboard charts,
// mobile off-canvas sidebar.

// Mobile/tablet off-canvas sidebar toggle (below 992px — see admin.css)
const sidebar = document.getElementById('adminSidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarClose = document.getElementById('sidebarClose');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');

function openSidebar() {
    sidebar.classList.add('show');
    sidebarBackdrop.classList.add('show');
    sidebarToggle.setAttribute('aria-expanded', 'true');
    // Lock the page behind the off-canvas menu so scrolling it doesn't
    // also scroll (or appear to "unfix") the background content.
    document.documentElement.classList.add('sidebar-open-lock');
}

function closeSidebar() {
    sidebar.classList.remove('show');
    sidebarBackdrop.classList.remove('show');
    sidebarToggle.setAttribute('aria-expanded', 'false');
    document.documentElement.classList.remove('sidebar-open-lock');
}

if (sidebar && sidebarToggle && sidebarBackdrop) {
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.contains('show') ? closeSidebar() : openSidebar();
    });
    if (sidebarClose) sidebarClose.addEventListener('click', closeSidebar);
    sidebarBackdrop.addEventListener('click', closeSidebar);
    // Close automatically when a nav link is tapped, so navigating doesn't
    // leave the off-canvas menu open over the new page.
    sidebar.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', closeSidebar);
    });
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 992) closeSidebar();
    });
}

// Stat totals count up once on load — the dashboard's one deliberate motion
// moment ("the ledger being tallied"), not a decorative flourish.
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

document.querySelectorAll('[data-count-target]').forEach(el => {
    const target = parseFloat(el.dataset.countTarget);
    const prefix = el.dataset.countPrefix || '';
    const decimals = parseInt(el.dataset.countDecimals || '0', 10);

    if (prefersReducedMotion || !isFinite(target)) {
        el.textContent = prefix + target.toFixed(decimals);
        return;
    }

    const duration = 900;
    const start = performance.now();

    function tick(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
        el.textContent = prefix + (target * eased).toFixed(decimals);
        if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
});

document.querySelectorAll('form.confirm-delete').forEach(form => {
    form.addEventListener('submit', (e) => {
        const message = form.dataset.confirmMessage || 'Are you sure? This cannot be undone.';
        if (!window.confirm(message)) {
            e.preventDefault();
        }
    });
});

// Dashboard charts (only present on the dashboard page, which loads Chart.js)
const donationChartEl = document.getElementById('donationTrendChart');
const memberChartEl = document.getElementById('memberGrowthChart');

if ((donationChartEl || memberChartEl) && window.Chart) {
    fetch('/admin/api/chart-data')
        .then(res => res.json())
        .then(data => {
            if (donationChartEl) {
                new Chart(donationChartEl, {
                    type: 'line',
                    data: {
                        labels: data.donation_trend.labels,
                        datasets: [{
                            label: 'Donations (GHS)',
                            data: data.donation_trend.values,
                            borderColor: '#C8973A',
                            backgroundColor: 'rgba(200,151,58,0.15)',
                            tension: 0.3,
                            fill: true
                        }]
                    },
                    options: { responsive: true, plugins: { legend: { display: false } } }
                });
            }

            if (memberChartEl) {
                new Chart(memberChartEl, {
                    type: 'bar',
                    data: {
                        labels: data.member_growth.labels,
                        datasets: [{
                            label: 'New Members',
                            data: data.member_growth.values,
                            backgroundColor: '#0D2B6B'
                        }]
                    },
                    options: { responsive: true, plugins: { legend: { display: false } } }
                });
            }
        })
        .catch(err => console.error('Failed to load chart data:', err));
}
