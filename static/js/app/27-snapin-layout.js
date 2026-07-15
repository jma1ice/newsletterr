// Snap-in source column: collapsible cards and the two-per-row grid.
//
// Collapse: every source card header carries a chevron toggle. Clicking it
// flips an `is-collapsed` class on the header (CSS hides the body and, for the
// header-only text/media cards, the button cluster). Default state is decided
// once at load with matchMedia: collapsed at <=768px, open above. No
// persistence; the user toggles freely per page load.
//
// Grid: the lighter source cards live in #snapin-grid (two columns at >=992px).
// Some cards sit inside wrapper divs (#droppedneedle-col, #yearly-wrapped-col,
// #coming-soon-col) that the pull scripts swap wholesale, and several wrappers
// render empty until their data is pulled. A pure :nth-child scheme cannot cope
// with that, so a small helper recounts the visible cards, hides empty
// wrappers, spans the last card across both columns when the count is odd, and
// stacks the internal halves of a card that is only half a column wide.
(function () {
    'use strict';

    var MOBILE = window.matchMedia('(max-width: 768px)');
    var TWO_COL = window.matchMedia('(min-width: 992px)');

    function isDisplayed(el) {
        return !!el && window.getComputedStyle(el).display !== 'none';
    }

    // A grid item counts as visible when it (or the builder-card it wraps) is
    // actually rendered. #ra-card manages its own inline display; wrapper divs
    // are empty until data lands.
    function itemVisible(el) {
        if (el.classList.contains('builder-card')) return isDisplayed(el);
        var card = el.querySelector('.builder-card');
        return isDisplayed(card);
    }

    function relayoutGrid() {
        var grid = document.getElementById('snapin-grid');
        if (!grid) return;

        var items = Array.prototype.filter.call(grid.children, function (el) {
            return el.nodeType === 1 && el.tagName !== 'INPUT';
        });

        var visible = [];
        items.forEach(function (el) {
            el.classList.remove('span-2');
            var vis = itemVisible(el);
            // Only the -col wrappers get force-hidden; builder-card items manage
            // their own display so we never fight #ra-card's inline style.
            if (!el.classList.contains('builder-card')) {
                el.classList.toggle('snapin-grid-hidden', !vis);
            }
            if (vis) visible.push(el);
        });

        var twoCol = TWO_COL.matches;
        if (twoCol && visible.length % 2 === 1) {
            visible[visible.length - 1].classList.add('span-2');
        }
    }

    function setCollapsed(header, collapsed) {
        header.classList.toggle('is-collapsed', collapsed);
        var btn = header.querySelector('.snapin-collapse-toggle');
        if (btn) btn.setAttribute('aria-expanded', String(!collapsed));
    }

    // Apply the default open/closed state to every card, once.
    function applyCollapseDefaults() {
        var collapsed = MOBILE.matches;
        document.querySelectorAll('#content-row .snapin-card-header').forEach(function (header) {
            setCollapsed(header, collapsed);
        });
    }

    // Click handling via delegation so pull-replaced cards keep working.
    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('.snapin-collapse-toggle');
        if (!btn) return;
        var header = btn.closest('.snapin-card-header');
        if (!header) return;
        setCollapsed(header, !header.classList.contains('is-collapsed'));
    });

    function init() {
        applyCollapseDefaults();
        relayoutGrid();

        // Pull scripts replaceWith the wrapper divs and toggle #ra-card's
        // display; re-run the grid layout whenever the grid subtree changes.
        var grid = document.getElementById('snapin-grid');
        if (grid && window.MutationObserver) {
            var pending = false;
            var obs = new MutationObserver(function () {
                if (pending) return;
                pending = true;
                window.requestAnimationFrame(function () {
                    pending = false;
                    relayoutGrid();
                });
            });
            // Watch childList (pull scripts replaceWith wrappers) and inline
            // style only (#ra-card display flips). relayoutGrid mutates classes,
            // not style, so this filter cannot retrigger itself into a loop.
            obs.observe(grid, { childList: true, subtree: true, attributes: true, attributeFilter: ['style'] });
        }

        var onBreakpoint = function () { relayoutGrid(); };
        if (TWO_COL.addEventListener) TWO_COL.addEventListener('change', onBreakpoint);
        else if (TWO_COL.addListener) TWO_COL.addListener(onBreakpoint);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
