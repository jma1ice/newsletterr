/*
 * App shell behavior, loaded on every page from base.html.
 *  - Desktop: collapse/expand the sidebar, persisted to localStorage['sidebar'].
 *    The collapsed class lives on <html> (documentElement) so the head
 *    flash-prevention script can restore it before first paint.
 *  - Mobile (<=768px): off-canvas drawer toggled by the hamburger in the
 *    slim top bar, dismissed by the scrim, Escape, or following a nav link.
 * Classic script sharing globals; no modules.
 */
(function () {
    var root = document.documentElement;

    // Alerts / audit blocks fade via the alertFadeOut CSS animation; once it
    // finishes, reclaim the layout space they held (CSS alone cannot, since a
    // faded-but-still-displayed box keeps its height).
    document.addEventListener('animationend', function (e) {
        if (e.animationName === 'alertFadeOut') e.target.style.display = 'none';
    });

    function setCollapsed(collapsed) {
        root.classList.toggle('sidebar-collapsed', collapsed);
        try { localStorage.setItem('sidebar', collapsed ? 'collapsed' : 'expanded'); } catch (e) {}
        var toggle = document.getElementById('sidebar-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', String(!collapsed));
    }

    function openDrawer(open) {
        document.body.classList.toggle('sidebar-open', open);
        var btn = document.getElementById('mobile-menu-btn');
        if (btn) btn.setAttribute('aria-expanded', String(open));
    }

    document.addEventListener('DOMContentLoaded', function () {
        var collapseBtn = document.getElementById('sidebar-toggle');
        if (collapseBtn) {
            collapseBtn.setAttribute('aria-expanded', String(!root.classList.contains('sidebar-collapsed')));
            collapseBtn.addEventListener('click', function () {
                setCollapsed(!root.classList.contains('sidebar-collapsed'));
            });
        }

        var menuBtn = document.getElementById('mobile-menu-btn');
        if (menuBtn) menuBtn.addEventListener('click', function () {
            openDrawer(!document.body.classList.contains('sidebar-open'));
        });

        var scrim = document.querySelector('.sidebar-scrim');
        if (scrim) scrim.addEventListener('click', function () { openDrawer(false); });

        // Following a nav link on mobile should close the drawer.
        var navLinks = document.getElementById('navLinks');
        if (navLinks) navLinks.addEventListener('click', function (e) {
            if (e.target.closest('a')) openDrawer(false);
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && document.body.classList.contains('sidebar-open')) openDrawer(false);
        });

        initSnapinsPaneResize();
        initConfigRowSticky();
    });

    // Builder page only (guarded by element presence): let the user drag the
    // snap-ins pane taller and remember the height. The native resize handle
    // sets an inline height only on a user drag, so persisting whenever an
    // inline height is present never records content-driven size changes.
    function paneCap() {
        return window.innerHeight - 96; // matches the CSS max-height cap
    }

    function clampPaneHeight(pane) {
        if (!pane.style.height) return;
        var h = parseInt(pane.style.height, 10);
        if (!isNaN(h) && h > paneCap()) pane.style.height = paneCap() + 'px';
    }

    function initSnapinsPaneResize() {
        var pane = document.getElementById('selected-items-pane');
        if (!pane) return;

        try {
            var saved = localStorage.getItem('snapinsHeight');
            if (saved) pane.style.height = saved;
        } catch (e) {}
        clampPaneHeight(pane);

        if (window.ResizeObserver) {
            var ro = new ResizeObserver(function () {
                if (pane.style.height) {
                    try { localStorage.setItem('snapinsHeight', pane.style.height); } catch (e) {}
                }
            });
            ro.observe(pane);
        }

        window.addEventListener('resize', function () { clampPaneHeight(pane); });
    }

    // Builder left rail (#config-row) is taller than the viewport, so a plain
    // top-sticky never reveals its bottom. Pin it with a negative-ish top so it
    // scrolls with the page until fully shown, then sticks. Recompute on size
    // and viewport changes; desktop widths only (the grid stacks at <=768px).
    function initConfigRowSticky() {
        var col = document.getElementById('config-row');
        if (!col) return;

        function update() {
            var desktop = window.matchMedia('(min-width: 769px)').matches;
            if (!desktop) {
                col.style.position = '';
                col.style.top = '';
                return;
            }
            var gap = 24; // ~ var(--space-5)
            var h = col.offsetHeight;
            col.style.position = 'sticky';
            if (h > window.innerHeight - gap) {
                col.style.top = (window.innerHeight - h - gap) + 'px';
            } else {
                col.style.top = gap + 'px';
            }
        }

        update();
        if (window.ResizeObserver) new ResizeObserver(update).observe(col);
        window.addEventListener('resize', update);
    }
})();
