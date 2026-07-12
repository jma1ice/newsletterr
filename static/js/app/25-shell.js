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
    });
})();
