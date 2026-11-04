// Admin newsletter pages: live email preview on the compose page, and
// one-click-only submit buttons. The server enforces send-once on its own
// (conditional status UPDATE); disabling the button just avoids confusion.

(function () {
    const form = document.getElementById('newsletterForm');
    const frame = document.getElementById('previewFrame');
    const state = document.getElementById('previewState');

    if (form && frame && window.fetch && window.FormData) {
        // JS is on: the preview follows typing, so the manual button is noise.
        form.querySelectorAll('.nl-nojs-preview').forEach(b => { b.hidden = true; });

        const url = form.dataset.previewUrl;
        let timer = null;
        let inFlight = null;
        let seq = 0;

        const setState = (text) => { if (state) state.textContent = text; };

        async function refresh() {
            const mine = ++seq;
            if (inFlight) inFlight.abort();
            inFlight = new AbortController();
            setState('Updating…');
            try {
                // FormData carries the form's csrf_token field.
                const res = await fetch(url, {
                    method: 'POST',
                    body: new FormData(form),
                    credentials: 'same-origin',
                    signal: inFlight.signal,
                    headers: { 'X-Requested-With': 'fetch' },
                });
                if (mine !== seq) return;
                if (res.redirected || !res.ok) {
                    setState(res.status === 429 ? 'Preview paused — typing too fast' : 'Preview unavailable — are you still signed in?');
                    return;
                }
                frame.srcdoc = await res.text();
                setState('Up to date');
            } catch (err) {
                if (err.name !== 'AbortError' && mine === seq) setState('Preview unavailable');
            }
        }

        form.addEventListener('input', () => {
            clearTimeout(timer);
            setState('Editing…');
            timer = setTimeout(refresh, 600);
        });
    }

    document.querySelectorAll('button[data-once]').forEach(btn => {
        const owner = btn.form;
        if (!owner) return;
        owner.addEventListener('submit', (e) => {
            if (btn.dataset.sent) { e.preventDefault(); return; }
            btn.dataset.sent = '1';
            // Disable after the submit is dispatched so the value still posts.
            setTimeout(() => {
                btn.disabled = true;
                btn.setAttribute('aria-busy', 'true');
            }, 0);
        });
    });
})();
