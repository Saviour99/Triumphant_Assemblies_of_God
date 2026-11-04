// Admin JS: mobile off-canvas sidebar, delete confirmations, dashboard
// figure count-up, dashboard charts, live activity polling.

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Money and counts are shown with thousands separators everywhere.
function formatNumber(value, decimals) {
    return Number(value).toLocaleString('en-GB', {
        minimumFractionDigits: decimals || 0,
        maximumFractionDigits: decimals || 0,
    });
}

// ============ OFF-CANVAS SIDEBAR (below 992px — see admin.css) ============
const sidebar = document.getElementById('adminSidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarClose = document.getElementById('sidebarClose');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');

function openSidebar() {
    sidebar.classList.add('show');
    sidebarBackdrop.classList.add('show');
    sidebarToggle.setAttribute('aria-expanded', 'true');
    // Lock the page behind the menu so scrolling the menu doesn't also
    // scroll (or appear to "unfix") the background content.
    document.documentElement.classList.add('sidebar-open-lock');
    const firstLink = sidebar.querySelector('.nav-link');
    if (firstLink) firstLink.focus({ preventScroll: true });
}

function closeSidebar(returnFocus) {
    if (!sidebar.classList.contains('show')) return;
    sidebar.classList.remove('show');
    sidebarBackdrop.classList.remove('show');
    sidebarToggle.setAttribute('aria-expanded', 'false');
    document.documentElement.classList.remove('sidebar-open-lock');
    if (returnFocus) sidebarToggle.focus();
}

if (sidebar && sidebarToggle && sidebarBackdrop) {
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.contains('show') ? closeSidebar(true) : openSidebar();
    });
    if (sidebarClose) sidebarClose.addEventListener('click', () => closeSidebar(true));
    sidebarBackdrop.addEventListener('click', () => closeSidebar(true));
    // Close when a link is tapped so navigating doesn't leave the menu open.
    sidebar.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => closeSidebar(false));
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSidebar(true);
    });
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 992) closeSidebar(false);
    });
}

// ============ FIGURE COUNT-UP ============
// The dashboard's one deliberate motion moment: totals tally up once on
// load. Skipped entirely under prefers-reduced-motion.
document.querySelectorAll('[data-count-target]').forEach(el => {
    const target = parseFloat(el.dataset.countTarget);
    const prefix = el.dataset.countPrefix || '';
    const decimals = parseInt(el.dataset.countDecimals || '0', 10);

    if (!isFinite(target)) return; // keep the server-rendered value
    if (prefersReducedMotion) {
        el.textContent = prefix + formatNumber(target, decimals);
        return;
    }

    const duration = 900;
    const start = performance.now();

    function tick(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
        el.textContent = prefix + formatNumber(target * eased, decimals);
        if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
});

// ============ DELETE / DEACTIVATE CONFIRMATION ============
document.querySelectorAll('form.confirm-delete').forEach(form => {
    form.addEventListener('submit', (e) => {
        const message = form.dataset.confirmMessage || 'Are you sure? This cannot be undone.';
        if (!window.confirm(message)) {
            e.preventDefault();
        }
    });
});

// ============ DASHBOARD CHARTS ============
// Two single-series line charts (separate charts, never a dual axis).
// Gold line is the darker brand gold (#A87A26) so a 2px stroke clears 3:1
// against white; area is a ~10% wash; gridlines are hairline and quiet;
// points only appear on hover unless there are few of them.
const donationChartEl = document.getElementById('donationTrendChart');
const memberChartEl = document.getElementById('memberGrowthChart');
let donationChart = null;
let memberChart = null;

const CHART_INK = '#667085';
const CHART_GRID = '#EEF0F3';
const CHART_FONT = "'Public Sans', system-ui, sans-serif";

function monthLabel(ym) {
    // '2025-03' -> 'Mar 2025'
    const [y, m] = String(ym).split('-').map(Number);
    if (!y || !m) return ym;
    return new Date(y, m - 1, 1).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
}

function compactCedis(v) {
    if (Math.abs(v) >= 10000) {
        return '₵' + Number(v).toLocaleString('en-GB', { notation: 'compact', maximumFractionDigits: 1 });
    }
    return '₵' + Number(v).toLocaleString('en-GB');
}

function baseLineOptions(yTicks, tooltipLabel) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: prefersReducedMotion ? false : { duration: 500 },
        interaction: { mode: 'index', intersect: false },
        layout: { padding: { top: 4 } },
        plugins: {
            legend: { display: false }, // single series: the panel title names it
            tooltip: {
                backgroundColor: '#FFFFFF',
                titleColor: '#172033',
                bodyColor: '#3E4759',
                borderColor: '#E2E5EB',
                borderWidth: 1,
                padding: 10,
                cornerRadius: 6,
                displayColors: false,
                titleFont: { family: CHART_FONT, weight: '600', size: 12 },
                bodyFont: { family: CHART_FONT, size: 12 },
                callbacks: { label: tooltipLabel },
            },
        },
        scales: {
            x: {
                grid: { display: false },
                border: { color: '#E2E5EB' },
                ticks: {
                    color: CHART_INK,
                    font: { family: CHART_FONT, size: 11 },
                    maxRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 6,
                },
            },
            y: {
                beginAtZero: true,
                grid: { color: CHART_GRID },
                border: { display: false },
                ticks: Object.assign({
                    color: CHART_INK,
                    font: { family: CHART_FONT, size: 11 },
                    maxTicksLimit: 5,
                    padding: 8,
                }, yTicks),
            },
        },
    };
}

function lineDataset(label, values, stroke, wash, showPoints) {
    return {
        label: label,
        data: values,
        borderColor: stroke,
        backgroundColor: wash,
        borderWidth: 2,
        borderCapStyle: 'round',
        borderJoinStyle: 'round',
        // 'monotone' gives a smooth curve without overshooting below zero.
        cubicInterpolationMode: 'monotone',
        pointRadius: showPoints ? 4 : 0,
        pointHoverRadius: 5,
        pointHitRadius: 12,
        pointBackgroundColor: stroke,
        pointBorderColor: '#FFFFFF',
        pointBorderWidth: 2,
        fill: true,
    };
}

// Dashboard auto-refresh requests are marked as background polls so the
// server doesn't treat them as admin activity (idle timeout still applies).
const BACKGROUND_POLL_HEADERS = { 'X-Background-Poll': '1' };

// If the admin session expired, the poll is redirected to the login page —
// reload so the admin sees the login screen instead of silent JSON errors.
function handlePollResponse(res) {
    if (res.redirected || res.status === 401 || res.status === 403) {
        window.location.reload();
        return Promise.reject(new Error('session expired'));
    }
    return res.json();
}

// Charts are created once, then updated in place on each refresh so the
// canvas doesn't flash/reset every cycle.
function loadChartData() {
    if (document.hidden) return;  // don't poll a background tab
    fetch('/admin/api/chart-data', { headers: BACKGROUND_POLL_HEADERS, credentials: 'same-origin' })
        .then(handlePollResponse)
        .then(data => {
            if (donationChartEl) {
                const labels = data.donation_trend.labels;
                const values = data.donation_trend.values;
                if (!donationChart) {
                    donationChart = new Chart(donationChartEl, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [lineDataset('Giving (GHS)', values, '#A87A26', 'rgba(200,151,58,0.10)', false)],
                        },
                        options: baseLineOptions(
                            { callback: v => compactCedis(v) },
                            ctx => '₵' + formatNumber(ctx.parsed.y, 2)
                        ),
                    });
                } else {
                    donationChart.data.labels = labels;
                    donationChart.data.datasets[0].data = values;
                    donationChart.update('none');
                }
            }

            if (memberChartEl) {
                const labels = data.member_growth.labels.map(monthLabel);
                const values = data.member_growth.values;
                if (!memberChart) {
                    memberChart = new Chart(memberChartEl, {
                        type: 'line',
                        data: {
                            labels: labels,
                            datasets: [lineDataset('Members', values, '#0D2B6B', 'rgba(13,43,107,0.08)', values.length <= 12)],
                        },
                        options: baseLineOptions(
                            { precision: 0, callback: v => formatNumber(v, 0) },
                            ctx => formatNumber(ctx.parsed.y, 0) + ' members'
                        ),
                    });
                } else {
                    memberChart.data.labels = labels;
                    memberChart.data.datasets[0].data = values;
                    memberChart.data.datasets[0].pointRadius = values.length <= 12 ? 4 : 0;
                    memberChart.update('none');
                }
            }
        })
        .catch(err => console.error('Failed to load chart data:', err));
}

if ((donationChartEl || memberChartEl) && window.Chart) {
    loadChartData();
    setInterval(loadChartData, 60000);
}

// ============ LIVE DASHBOARD ACTIVITY ============
// Polls for new donations/registrations every few seconds so an admin
// watching the dashboard sees them without a manual refresh — works no
// matter which path completed the donation (client-side verify or the
// Paystack webhook), since it just reflects current DB state.
// Row markup must match dashboard.html (.activity-item > .activity-main +
// .activity-meta).
(function initLiveDashboardActivity() {
    const activityList = document.getElementById('recentActivityList');
    const donationsList = document.getElementById('recentDonationsList');
    if (!activityList && !donationsList) return; // not on the dashboard page

    function idsOf(listEl, attr) {
        if (!listEl) return new Set();
        return new Set(Array.from(listEl.querySelectorAll(`[${attr}]`)).map(el => el.getAttribute(attr)));
    }

    let knownActivityIds = idsOf(activityList, 'data-activity-id');
    let knownDonationIds = idsOf(donationsList, 'data-donation-id');

    function titleCase(str) {
        return (str || '').replace(/\w\S*/g, w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
    }

    function updateStat(key, value, decimals, prefix) {
        const el = document.querySelector(`[data-stat="${key}"]`);
        if (el) el.textContent = (prefix || '') + formatNumber(value, decimals || 0);
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function renderList(listEl, items, idAttr, knownIds, emptyText, buildRow, latestBadgeText) {
        if (!listEl) return;
        listEl.innerHTML = '';
        if (!items.length) {
            listEl.appendChild(el('li', 'activity-empty', emptyText));
            return;
        }
        items.forEach((item, index) => {
            const li = buildRow(item);
            li.className = 'activity-item';
            li.setAttribute(idAttr, item.id);
            if (!knownIds.has(String(item.id))) {
                li.classList.add('newly-added');
            }
            // The newest row always carries the tag, same as first load.
            if (index === 0 && latestBadgeText) {
                li.firstElementChild.appendChild(el('span', 'badge-latest', latestBadgeText));
            }
            listEl.appendChild(li);
        });
    }

    function pollRecentActivity() {
        if (document.hidden) return;  // don't poll a background tab
        fetch('/admin/api/recent-activity', { headers: BACKGROUND_POLL_HEADERS, credentials: 'same-origin' })
            .then(handlePollResponse)
            .then(data => {
                updateStat('total_members', data.total_members);
                updateStat('total_donations', data.total_donations, 2, '₵');
                updateStat('total_prayer_requests', data.total_prayer_requests);
                updateStat('total_messages', data.total_messages);
                updateStat('total_newsletter_subscribers', data.total_newsletter_subscribers);
                updateStat('total_devotions', data.total_devotions);

                renderList(activityList, data.recent_activity, 'data-activity-id', knownActivityIds, 'No new members or messages yet.', item => {
                    const li = document.createElement('li');
                    const main = el('span', 'activity-main');
                    const icon = el('i', `fa-solid ${item.type === 'registration' ? 'fa-user-plus' : 'fa-envelope'} activity-type-icon activity-type-icon-${item.type}`);
                    icon.setAttribute('aria-hidden', 'true');
                    main.append(icon, el('span', 'activity-main-text', item.type === 'registration' ? titleCase(item.title) : item.title));
                    li.append(main, el('span', 'activity-meta', item.detail));
                    return li;
                }, 'Newest');
                knownActivityIds = new Set(data.recent_activity.map(item => String(item.id)));

                renderList(donationsList, data.recent_donations, 'data-donation-id', knownDonationIds, 'No completed gifts yet.', d => {
                    const li = document.createElement('li');
                    const main = el('span', 'activity-main');
                    const icon = el('i', 'fa-solid fa-hand-holding-dollar activity-type-icon activity-type-icon-donation');
                    icon.setAttribute('aria-hidden', 'true');
                    const text = el('span', 'activity-main-text', titleCase(d.donor_name) + ' ');
                    text.appendChild(el('span', 'activity-sub', titleCase((d.giving_type || '').replace(/_/g, ' '))));
                    main.append(icon, text);
                    li.append(main, el('span', 'activity-meta activity-amount', '₵' + formatNumber(d.amount, 2)));
                    return li;
                }, 'Latest');
                knownDonationIds = new Set(data.recent_donations.map(d => String(d.id)));
            })
            .catch(err => console.error('Failed to poll recent activity:', err));
    }

    // 30s (was 5s): background polls don't extend the admin idle timeout
    // (X-Background-Poll header), and hidden tabs skip polling entirely.
    setInterval(pollRecentActivity, 30000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) pollRecentActivity();
    });
})();
