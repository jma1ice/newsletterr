// Snap-in source column: collapsible cards and the two-per-row grid.
//
// Collapse: every source card header carries a chevron toggle. Clicking it
// flips an `is-collapsed` class on the header (CSS hides the body and, for the
// header-only text/media cards, the button cluster). Default state is decided
// once at load with matchMedia: collapsed at <=768px, open above. No
// persistence; the user toggles freely per page load.
//
// Grid: the lighter source cards live in #snapin-grid (two columns once the
// source column is wide enough, via a container query in builder.css). Some
// cards sit inside wrapper divs (#droppedneedle-col, #yearly-wrapped-col,
// #coming-soon-col) that the pull scripts swap wholesale, and several wrappers
// render empty until their data is pulled. A pure :nth-child scheme cannot cope
// with that, so a small helper recounts the visible cards and hides empty
// wrappers.
//
// Masonry: in two-column mode the grid uses tiny fixed implicit rows
// (grid-auto-rows in builder.css) and this helper gives every visible card a
// grid-row span covering its measured height plus one visual gap. Cards then
// pack up under the shorter column instead of aligning to the tallest card in
// their row, which is what left a large hole under a short card. A
// ResizeObserver re-runs the layout when any card's height changes (collapse
// toggles, posters loading, column resizes).
(function () {
    'use strict';

    var MOBILE = window.matchMedia('(max-width: 768px)');

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

    // Style writes are guarded with a changed-check so the MutationObserver
    // watching style attributes settles after one echo instead of looping.
    function setRowSpan(el, value) {
        if (el.style.gridRowEnd !== value) el.style.gridRowEnd = value;
    }

    function relayoutGrid() {
        var grid = document.getElementById('snapin-grid');
        if (!grid) return;

        var items = Array.prototype.filter.call(grid.children, function (el) {
            return el.nodeType === 1 && el.tagName !== 'INPUT';
        });

        var visible = [];
        items.forEach(function (el) {
            var vis = itemVisible(el);
            // Only the -col wrappers get force-hidden; builder-card items manage
            // their own display so we never fight #ra-card's inline style.
            if (!el.classList.contains('builder-card')) {
                el.classList.toggle('snapin-grid-hidden', !vis);
            }
            if (vis) visible.push(el);
            observeItem(el);
        });

        // The column count is decided by a container query, so read it off the
        // grid's computed style instead of a viewport breakpoint.
        var style = window.getComputedStyle(grid);
        var twoCol = style.gridTemplateColumns.trim().indexOf(' ') !== -1;

        // Masonry spans. An odd trailing card simply packs into the shorter
        // column like everything else; spanning it across both columns (the
        // old odd-count rule) would push it below the taller column and
        // reopen the very hole the spans exist to close. In single-column
        // mode grid-auto-rows computes to auto (NaN here) and all spans are
        // cleared so normal flow and the grid gap take over.
        var rowH = parseFloat(style.gridAutoRows);
        var vgap = parseFloat(style.columnGap) || 0;
        items.forEach(function (el) {
            if (twoCol && rowH > 0 && visible.indexOf(el) !== -1) {
                var h = el.getBoundingClientRect().height;
                setRowSpan(el, 'span ' + Math.max(1, Math.ceil((h + vgap) / rowH)));
            } else {
                setRowSpan(el, '');
            }
        });
    }

    var relayoutPending = false;
    function scheduleRelayout() {
        if (relayoutPending) return;
        relayoutPending = true;
        window.requestAnimationFrame(function () {
            relayoutPending = false;
            relayoutGrid();
        });
    }

    // Card heights change outside our sight (collapse toggles, posters
    // loading, the source column resizing), and every change needs fresh row
    // spans. Each grid item is observed once; replaced items fall away with
    // the WeakSet. The observe() initial callback just echoes one relayout.
    var itemObserver = window.ResizeObserver ? new ResizeObserver(scheduleRelayout) : null;
    var observedItems = itemObserver ? new WeakSet() : null;
    function observeItem(el) {
        if (!itemObserver || observedItems.has(el)) return;
        observedItems.add(el);
        itemObserver.observe(el);
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
            var obs = new MutationObserver(scheduleRelayout);
            // Watch childList (pull scripts replaceWith wrappers) and inline
            // style (#ra-card display flips, our own grid-row spans). The
            // changed-check in setRowSpan keeps our writes from retriggering
            // this into a loop.
            obs.observe(grid, { childList: true, subtree: true, attributes: true, attributeFilter: ['style'] });
        }

        // Fallback for browsers without ResizeObserver; otherwise the per-item
        // observer already covers width-driven height changes.
        if (!itemObserver) window.addEventListener('resize', scheduleRelayout);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
