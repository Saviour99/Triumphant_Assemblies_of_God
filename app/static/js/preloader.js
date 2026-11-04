/* ============================================
   PRELOADER
   Loaded synchronously in <head> (tiny, no dependencies) so it can decide
   before the first paint whether the preloader shows at all:
   - Adds .js to <html> (the preloader stays hidden without JS).
   - Shows it (.tag-preload on <html>) only on the first page view of a
     browser session, so moving between pages is never slowed down.
   - Hides it on DOMContentLoaded (never waits for images/the hero video),
     after a short minimum so the intro doesn't just flicker, with a hard
     cap as a failsafe. Reduced motion: hidden instantly, no fade.
   ============================================ */
(function () {
    'use strict';

    var root = document.documentElement;
    root.classList.add('js');

    var SESSION_KEY = 'tag-preloader-seen';
    var MIN_VISIBLE_MS = 550;  // lets the gold rule finish drawing
    var HARD_CAP_MS = 1200;    // failsafe: fade starts no later than this
    var FADE_MS = 360;         // matches the transition in preloader.css

    var firstVisit = false;
    try {
        if (!window.sessionStorage.getItem(SESSION_KEY)) {
            window.sessionStorage.setItem(SESSION_KEY, '1');
            firstVisit = true;
        }
    } catch (e) {
        // Storage blocked (private mode, disabled site data): skip the
        // preloader rather than show it on every page.
        firstVisit = false;
    }
    if (!firstVisit) return;

    root.classList.add('tag-preload');

    var reduceMotion = !!(window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    var start = Date.now();
    var done = false;

    function remove() {
        var el = document.getElementById('preloader');
        if (el && el.parentNode) el.parentNode.removeChild(el);
        root.classList.remove('tag-preload');
    }

    function hide() {
        if (done) return;
        done = true;
        var el = document.getElementById('preloader');
        if (!el || reduceMotion) { remove(); return; }
        el.classList.add('is-leaving');
        var finished = false;
        function finish() {
            if (finished) return;
            finished = true;
            remove();
        }
        el.addEventListener('transitionend', function (ev) {
            if (ev.target === el && ev.propertyName === 'opacity') finish();
        });
        setTimeout(finish, FADE_MS + 120);
    }

    function onReady() {
        if (reduceMotion) { hide(); return; }
        var wait = Math.max(0, MIN_VISIBLE_MS - (Date.now() - start));
        setTimeout(hide, wait);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
    setTimeout(hide, HARD_CAP_MS);
})();
