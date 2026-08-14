// Rich text editing for the text/title/header snap-ins.
(function () {
    'use strict';

    var SURFACE = '.text-block-editor';

    function surfaceFor(id) {
        return document.querySelector(SURFACE + '[data-textblock-id="' + CSS.escape(id) + '"]');
    }

    // execCommand is deprecated but is still the only cross-browser way to
    // apply formatting to a selection without hand-rolling range surgery. It
    // is not blocked by CSP.
    function exec(command, value) {
        try {
            document.execCommand(command, false, value === undefined ? null : value);
        } catch (e) {
            console.warn('formatting command failed:', command, e);
        }
    }

    // Emit tags (<b>, <i>, <u>) rather than inline styles.
    //
    // styleWithCSS looked like the tidier option, but with it on the browser
    // copies the *editor's own* computed styling into the content it rewrites:
    // applying an alignment re-wrapped the text in spans carrying
    // `font-size: 0.9rem`, which is the builder's editor size, and that would
    // have shipped into the email and overridden the block's real size. Tags
    // carry no such baggage, and every mail client understands them.
    function preferTags() {
        try { document.execCommand('styleWithCSS', false, false); } catch (e) { /* older browsers */ }
    }

    // Whatever the browser does emit, the editor's own typography has no
    // business in the email: font size and family are set per block, never on
    // a selection, so an inline one here is always an artifact of the
    // contenteditable surface copying its own computed style.
    // Done through the DOM rather than a regex, so a font-size inside text
    // content or an attribute value cannot be mangled by accident.
    var ARTIFACT_PROPS = ['font-size', 'font-family'];

    // Text blocks are centred by default, which leaves a list's markers
    // pinned to the far left of the block while the item text sits in the
    // middle - on a short item the bullet can end up an inch from its own
    // words. Shrink-wrapping the list with inline-block lets the parent
    // centre it as a unit, and text-align: left keeps each marker next to
    // its text. Applied to the element so it survives into the email, where
    // no stylesheet of ours reaches.
    function normalizeList(list) {
        if (!list) return;
        if (!list.style.display) list.style.display = 'inline-block';
        if (!list.style.textAlign) list.style.textAlign = 'left';
        if (!list.style.margin) list.style.margin = '0';
        if (!list.style.paddingLeft) list.style.paddingLeft = '1.5em';
    }

    function stripEditorArtifacts(html) {
        var scratch = document.createElement('div');
        scratch.innerHTML = String(html || '');
        scratch.querySelectorAll('[style]').forEach(function (el) {
            ARTIFACT_PROPS.forEach(function (prop) { el.style.removeProperty(prop); });
            if (!el.getAttribute('style')) el.removeAttribute('style');
        });
        scratch.querySelectorAll('ul, ol').forEach(normalizeList);
        return scratch.innerHTML;
    }

    // Every <a> the selection touches. Link appearance lives on the anchor
    // itself, so the underline and colour controls need the elements rather
    // than the selection.
    function anchorsInSelection(surface) {
        var sel = document.getSelection();
        var found = [];
        if (!sel || sel.rangeCount === 0) return found;
        var range = sel.getRangeAt(0);
        surface.querySelectorAll('a').forEach(function (a) {
            try {
                if (range.intersectsNode(a)) found.push(a);
            } catch (e) { /* detached node */ }
        });
        if (!found.length && sel.anchorNode) {
            var el = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
            var a = el && el.closest ? el.closest('a') : null;
            if (a && surface.contains(a)) found.push(a);
        }
        return found;
    }

    window.stripEditorArtifacts = stripEditorArtifacts;

    function activeSurface() {
        var node = document.getSelection && document.getSelection().anchorNode;
        if (!node) return null;
        var el = node.nodeType === 1 ? node : node.parentElement;
        return el && el.closest ? el.closest(SURFACE) : null;
    }

    // After a command runs, push the surface's HTML into the model without
    // re-rendering the row.
    function syncFromSurface(surface) {
        if (!surface) return;
        var id = surface.dataset.textblockId;
        var wrapper = surface.closest('.selected-item');
        var index = wrapper ? parseInt(wrapper.dataset.index, 10) : NaN;
        if (!Number.isNaN(index) && typeof updateTextBlockName === 'function') {
            updateTextBlockName(id, index);
        }
    }

    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('.rte-btn');
        if (!btn) return;
        e.preventDefault();

        var id = btn.dataset.textblockId;
        var surface = surfaceFor(id);
        if (!surface) return;

        // The toolbar button steals focus on mousedown-less clicks in some
        // browsers; restore it so the command lands on the right selection.
        if (activeSurface() !== surface) surface.focus();

        preferTags();

        var command = btn.dataset.cmd;

        // Mail clients underline links by default and nothing in execCommand
        // touches that, so the anchor is styled directly. Toggling off writes
        // an explicit `text-decoration: none`, which beats the client default.
        if (command === 'linkUnderline') {
            var anchors = anchorsInSelection(surface);
            if (!anchors.length) return;
            var turningOff = anchors[0].style.textDecoration !== 'none';
            anchors.forEach(function (a) {
                if (turningOff) a.style.textDecoration = 'none';
                else a.style.removeProperty('text-decoration');
                if (!a.getAttribute('style')) a.removeAttribute('style');
            });
            syncFromSurface(surface);
            refreshToolbarState(surface);
            return;
        }

        if (command === 'createLink') {
            var url = window.prompt('Link URL:', 'https://');
            if (!url || !url.trim()) return;
            exec('createLink', url.trim());
            // execCommand does not set target; do it so the link opens away
            // from the reader's mail client.
            var anchor = activeSurface() && document.getSelection().anchorNode;
            var el = anchor && (anchor.nodeType === 1 ? anchor : anchor.parentElement);
            var link = el && el.closest ? el.closest('a') : null;
            if (link) {
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener noreferrer');
            }
        } else {
            exec(command);
        }

        // Style a freshly created list straight away, so the editor shows the
        // same thing the email will rather than only fixing it on next read.
        if (command === 'insertUnorderedList' || command === 'insertOrderedList') {
            surface.querySelectorAll('ul, ol').forEach(normalizeList);
        }

        syncFromSurface(surface);
        refreshToolbarState(surface);
    });

    // Toolbar buttons must not take focus away from the selection, or the
    // command applies to nothing.
    document.addEventListener('mousedown', function (e) {
        if (e.target.closest && e.target.closest('.rte-btn')) e.preventDefault();
    });

    // The colour swatch is the exception: preventing default would stop the
    // native picker opening. Remember the selection instead and put it back
    // before applying, since opening the picker collapses it.
    var savedRange = null;
    var savedSurfaceId = null;

    document.addEventListener('mousedown', function (e) {
        var swatch = e.target.closest && e.target.closest('.rte-color');
        if (!swatch) return;
        var sel = document.getSelection();
        savedRange = (sel && sel.rangeCount) ? sel.getRangeAt(0).cloneRange() : null;
        savedSurfaceId = swatch.dataset.textblockId;
    }, true);

    function restoreSelection() {
        if (!savedRange) return false;
        var sel = document.getSelection();
        sel.removeAllRanges();
        sel.addRange(savedRange);
        return true;
    }

    document.addEventListener('input', function (e) {
        var swatch = e.target.closest && e.target.closest('.rte-color');
        if (!swatch) return;
        var surface = surfaceFor(swatch.dataset.textblockId || savedSurfaceId);
        if (!surface) return;

        surface.focus();
        if (!restoreSelection()) return;

        // foreColor as CSS rather than a <font> tag: a span carrying `color`
        // is what the sanitizer keeps and what every client honours. Any
        // font-size the browser copies in alongside is stripped on read.
        try { document.execCommand('styleWithCSS', false, true); } catch (err) { /* older browsers */ }
        exec('foreColor', swatch.value);
        try { document.execCommand('styleWithCSS', false, false); } catch (err) { /* older browsers */ }

        // A link keeps the client's own colour unless the anchor itself says
        // otherwise, so colour the <a> too when the selection is inside one.
        anchorsInSelection(surface).forEach(function (a) {
            a.style.color = swatch.value;
        });

        syncFromSurface(surface);
    });

    // Paste as plain text. This is the single most important rule here: a
    // paste from Word or a web page otherwise injects markup that renders
    // unpredictably in mail clients and bloats the email.
    document.addEventListener('paste', function (e) {
        var surface = e.target.closest && e.target.closest(SURFACE);
        if (!surface) return;
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData('text/plain') || '';
        // insertText keeps the caret and the undo stack intact.
        exec('insertText', text);
        syncFromSurface(surface);
    });

    // Enter inserts a line break rather than a new block: a text snap-in is
    // one block, and <div> soup is what makes pasted email HTML unreadable.
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || e.shiftKey) return;
        var surface = e.target.closest && e.target.closest(SURFACE);
        if (!surface) return;
        e.preventDefault();
        exec('insertLineBreak');
        syncFromSurface(surface);
    });

    // Reflect the caret's current formatting on the toolbar.
    function refreshToolbarState(surface) {
        if (!surface) return;
        var id = surface.dataset.textblockId;
        var anchors = anchorsInSelection(surface);
        document.querySelectorAll('.rte-btn[data-textblock-id="' + CSS.escape(id) + '"]').forEach(function (btn) {
            var command = btn.dataset.cmd;
            if (command === 'createLink' || command === 'removeFormat') return;

            var on;
            if (command === 'linkUnderline') {
                // Only meaningful inside a link; lit means the link is
                // underlined, which is the client default.
                btn.disabled = anchors.length === 0;
                on = anchors.length > 0 && anchors[0].style.textDecoration !== 'none';
            } else {
                try { on = document.queryCommandState(command); } catch (err) { on = false; }
            }
            btn.classList.toggle('is-active', !!on);
            btn.setAttribute('aria-pressed', String(!!on));
        });
    }

    document.addEventListener('selectionchange', function () {
        refreshToolbarState(activeSurface());
    });

    window.refreshRichTextToolbar = refreshToolbarState;
})();
