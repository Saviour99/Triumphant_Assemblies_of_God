/* Giving thank-you / receipt page (public/payment_received.html).
 * - Print receipt button -> window.print()
 * - Copy reference (navigator.clipboard, with a selection + execCommand fallback)
 * - Pending state: polls POST /api/paystack/verify (CSRF header, same as the
 *   giving form) every POLL_MS for up to MAX_MS, reloading as soon as the
 *   server reports a final state. The verify endpoint is limited to
 *   10/minute per client, so the interval stays above 6s on purpose.
 */
(function () {
    'use strict';

    var POLL_MS = 8000;
    var MAX_MS = 60000;

    function $(id) { return document.getElementById(id); }

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    // ---------- Print ----------
    var printBtn = $('payPrint');
    if (printBtn) {
        printBtn.addEventListener('click', function () { window.print(); });
    }

    // ---------- Copy reference ----------
    var copyBtn = $('payCopy');
    if (copyBtn) {
        var copyMsg = $('payCopyMsg');
        var clearTimer = null;
        var announce = function (text) {
            copyMsg.textContent = text;
            clearTimeout(clearTimer);
            clearTimer = setTimeout(function () { copyMsg.textContent = ''; }, 3000);
        };
        var fallbackCopy = function (el) {
            try {
                var range = document.createRange();
                range.selectNodeContents(el);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                var ok = document.execCommand && document.execCommand('copy');
                sel.removeAllRanges();
                return !!ok;
            } catch (e) {
                return false;
            }
        };
        copyBtn.addEventListener('click', function () {
            var el = $(copyBtn.getAttribute('data-copy-target'));
            if (!el) return;
            var text = el.textContent.trim();
            var onFail = function () {
                announce(fallbackCopy(el) ? 'Copied' : 'Press Ctrl+C (or Cmd+C) to copy the selected reference');
            };
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(function () { announce('Copied'); }, onFail);
            } else {
                onFail();
            }
        });
    }

    // ---------- Pending: poll verify ----------
    var pending = $('payPending');
    if (!pending) return;

    var reference = pending.getAttribute('data-reference');
    var verifyUrl = pending.getAttribute('data-verify-url');
    var msg = $('payPollMsg');
    var againBtn = $('payCheckAgain');
    var startedAt = Date.now();
    var timer = null;
    var inFlight = false;

    function setMsg(text) { if (msg) msg.textContent = text; }

    // A 400 can also mean "paid, but amount/currency mismatch": the gift
    // then stays pending for manual review, so a reload would land back
    // here. Cap reloads per reference so that can't become a reload loop.
    var RELOAD_KEY = 'payReloads:' + reference;
    function reloadCount() {
        try { return parseInt(sessionStorage.getItem(RELOAD_KEY) || '0', 10) || 0; } catch (e) { return 0; }
    }

    function finish(confirmed) {
        // The server now has a final state (completed/failed/unknown):
        // reload so it renders that state.
        var n = reloadCount();
        if (!confirmed && n >= 2) {
            setMsg('We still could not confirm this payment automatically. Please contact the church office with the reference above.');
            return false;
        }
        try { sessionStorage.setItem(RELOAD_KEY, String(n + 1)); } catch (e) { /* storage blocked */ }
        setMsg('Update received. Loading your receipt…');
        window.location.reload();
        return true;
    }

    function schedule() {
        clearTimeout(timer);
        if (Date.now() - startedAt + POLL_MS > MAX_MS) {
            setMsg('Paystack is taking longer than usual. Your gift is safe; use "Check again" in a moment, or come back to this page later.');
            return;
        }
        timer = setTimeout(check, POLL_MS);
    }

    function check(manual) {
        if (inFlight) return;
        inFlight = true;
        if (againBtn) againBtn.disabled = true;
        if (manual) setMsg('Checking with Paystack…');

        fetch(verifyUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ reference: reference })
        })
            .then(function (res) {
                // 200 = completed, 400 = failed/not verifiable, 404 = unknown:
                // all final, so let the server render the outcome.
                if (res.status === 200 || res.status === 400 || res.status === 404) {
                    finish(res.status === 200);
                    return; // no further auto-polling either way
                }
                // 202 still pending; 429/5xx transient. Keep waiting.
                if (manual) setMsg('Still confirming. This page will keep checking.');
                schedule();
            })
            .catch(function () {
                if (manual) setMsg('We could not reach the server. Check your connection and try again.');
                schedule();
            })
            .then(function () {
                inFlight = false;
                if (againBtn) againBtn.disabled = false;
            });
    }

    if (againBtn) {
        againBtn.addEventListener('click', function () {
            clearTimeout(timer);
            // A manual check restarts the auto-poll window.
            startedAt = Date.now();
            check(true);
        });
    }

    schedule();
})();
