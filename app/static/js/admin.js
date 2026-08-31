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
                            backgroundColor: 'rgba(200,151,58,0.10)',
                            borderWidth: 2,
                            borderCapStyle: 'round',
                            borderJoinStyle: 'round',
                            // 'monotone' — not raw bezier tension — is what gives a
                            // genuinely smooth, flowing curve without the overshoot
                            // dips/wobbles plain tension can introduce between points.
                            cubicInterpolationMode: 'monotone',
                            pointRadius: 4,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#C8973A',
                            pointBorderColor: '#fff',
                            pointBorderWidth: 2,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        interaction: { mode: 'index', intersect: false },
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { grid: { display: false } },
                            y: {
                                beginAtZero: true,
                                grid: { color: 'rgba(0,0,0,0.06)' },
                                ticks: { callback: v => '₵' + v.toLocaleString() }
                            }
                        }
                    }
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
                            backgroundColor: '#0D2B6B',
                            borderRadius: 4,
                            maxBarThickness: 24
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { grid: { display: false } },
                            y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.06)' }, ticks: { precision: 0 } }
                        }
                    }
                });
            }
        })
        .catch(err => console.error('Failed to load chart data:', err));
}

// ============ LIVE DASHBOARD ACTIVITY ============
// Polls for new donations/registrations every few seconds so an admin
// watching the dashboard sees them without a manual refresh — works no
// matter which path completed the donation (client-side verify or the
// Paystack webhook), since it just reflects current DB state.
(function initLiveDashboardActivity() {
    const registrationsList = document.getElementById('recentRegistrationsList');
    const donationsList = document.getElementById('recentDonationsList');
    if (!registrationsList && !donationsList) return; // not on the dashboard page

    function idsOf(listEl, attr) {
        if (!listEl) return new Set();
        return new Set(Array.from(listEl.querySelectorAll(`[${attr}]`)).map(el => el.getAttribute(attr)));
    }

    let knownMemberIds = idsOf(registrationsList, 'data-member-id');
    let knownDonationIds = idsOf(donationsList, 'data-donation-id');

    function titleCase(str) {
        return (str || '').replace(/\w\S*/g, w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
    }

    function updateStat(key, value, decimals, prefix) {
        const el = document.querySelector(`[data-stat="${key}"]`);
        if (el) el.textContent = (prefix || '') + Number(value).toFixed(decimals || 0);
    }

    function renderList(listEl, items, idAttr, knownIds, emptyText, buildRow, latestBadgeText) {
        if (!listEl) return;
        if (!items.length) {
            listEl.innerHTML = '';
            const li = document.createElement('li');
            li.className = 'list-group-item text-muted';
            li.textContent = emptyText;
            listEl.appendChild(li);
            return;
        }
        listEl.innerHTML = '';
        items.forEach((item, index) => {
            const li = buildRow(item);
            li.className = 'list-group-item d-flex justify-content-between';
            li.setAttribute(idAttr, item.id);
            if (!knownIds.has(String(item.id))) {
                li.classList.add('newly-added');
            }
            // The newest row (index 0) always carries the "Latest"/"Newest"
            // tag — not just rows that are new since the last poll — same
            // as the server-rendered first-load state.
            if (index === 0 && latestBadgeText) {
                const badge = document.createElement('span');
                badge.className = 'badge-latest ms-2';
                badge.textContent = latestBadgeText;
                li.firstElementChild.appendChild(badge);
            }
            listEl.appendChild(li);
        });
    }

    function pollRecentActivity() {
        fetch('/admin/api/recent-activity')
            .then(res => res.json())
            .then(data => {
                updateStat('total_members', data.total_members);
                updateStat('total_donations', data.total_donations, 2, '₵');
                updateStat('total_prayer_requests', data.total_prayer_requests);
                updateStat('total_messages', data.total_messages);
                updateStat('total_newsletter_subscribers', data.total_newsletter_subscribers);
                updateStat('total_devotions', data.total_devotions);

                renderList(registrationsList, data.recent_registrations, 'data-member-id', knownMemberIds, 'No members yet.', m => {
                    const li = document.createElement('li');
                    const nameSpan = document.createElement('span');
                    nameSpan.textContent = titleCase(m.full_name);
                    const dateSpan = document.createElement('span');
                    dateSpan.className = 'text-muted small';
                    dateSpan.textContent = m.created_at;
                    li.append(nameSpan, dateSpan);
                    return li;
                }, 'Newest');
                knownMemberIds = new Set(data.recent_registrations.map(m => String(m.id)));

                renderList(donationsList, data.recent_donations, 'data-donation-id', knownDonationIds, 'No donations yet.', d => {
                    const li = document.createElement('li');
                    const nameSpan = document.createElement('span');
                    nameSpan.textContent = `${titleCase(d.donor_name)} (${titleCase(d.giving_type)})`;
                    const amountSpan = document.createElement('span');
                    amountSpan.className = 'text-muted small';
                    amountSpan.textContent = `₵${Number(d.amount).toFixed(2)}`;
                    li.append(nameSpan, amountSpan);
                    return li;
                }, 'Latest');
                knownDonationIds = new Set(data.recent_donations.map(d => String(d.id)));
            })
            .catch(err => console.error('Failed to poll recent activity:', err));
    }

    setInterval(pollRecentActivity, 15000);
})();
