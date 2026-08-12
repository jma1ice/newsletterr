(function () {
    const KEY = 'newsletterr_draft';
    let dirty = false;
    let restoring = false;

    const $ = (id) => document.getElementById(id);

    let baseline = null;

    function snapshot() {
        // The captured chart PNG never goes in the draft: restoring one would
        // put a picture of last session's data back in the builder, and a few
        // base64 charts are enough to blow the localStorage quota. A restored
        // graph re-captures from current data on the first preview.
        const items = (typeof selectedItems !== 'undefined') ? selectedItems : [];
        return {
            subject: $('subject')?.value || '',
            header: $('email_header_title')?.value || '',
            customHtml: $('custom-html-editor')?.value || '',
            items: items.map(({ chartImage, chartGen, ...rest }) => rest),
            ts: Date.now(),
        };
    }

    function signature(snap) {
        return JSON.stringify({
            subject: snap.subject,
            header: snap.header,
            customHtml: snap.customHtml,
            items: snap.items || [],
        });
    }

    function saveDraft() {
        if (restoring) return;
        try {
            const snap = snapshot();
            const hasContent = snap.subject || snap.header || (snap.items && snap.items.length);
            if (!hasContent) return;
            localStorage.setItem(KEY, JSON.stringify(snap));
            dirty = baseline !== null && signature(snap) !== baseline;
        } catch (e) {
            /* storage full or unavailable: ignore */
        }
    }

    window.markDraftClean = function () {
        try {
            baseline = signature(snapshot());
        } catch (e) {
            baseline = null;
        }
        dirty = false;
    };

    const debouncedSave = (typeof debounce === 'function') ? debounce(saveDraft, 500) : saveDraft;

    window.clearDraft = function () {
        try { localStorage.removeItem(KEY); } catch (e) {}
        window.markDraftClean();
    };

    function restoreDraft() {
        let draft;
        try {
            draft = JSON.parse(localStorage.getItem(KEY) || 'null');
        } catch (e) {
            return;
        }
        if (!draft) return;

        const builderEmpty = (typeof selectedItems === 'undefined' || !selectedItems.length)
            && !($('custom-html-editor')?.value);
        if (!builderEmpty) return;  // do not clobber an already-populated builder

        const when = new Date(draft.ts || Date.now()).toLocaleString();
        if (!window.confirm(`Restore your unsaved newsletter draft from ${when}?`)) {
            window.clearDraft();
            return;
        }

        restoring = true;
        try {
            if ($('subject')) $('subject').value = draft.subject || '';
            if ($('email_header_title')) $('email_header_title').value = draft.header || '';
            if (draft.customHtml && $('custom-html-editor')) $('custom-html-editor').value = draft.customHtml;
            if (Array.isArray(draft.items) && typeof selectedItems !== 'undefined') {
                selectedItems.length = 0;
                draft.items.forEach(i => selectedItems.push(i));
                if (typeof updateSelectedItemsDisplay === 'function') updateSelectedItemsDisplay();
                if (typeof updatePreview === 'function') updatePreview();
            }
        } catch (e) {
            console.error('Draft restore failed:', e);
            window.clearDraft();
        } finally {
            restoring = false;
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        restoreDraft();
        window.markDraftClean();

        ['subject', 'email_header_title', 'custom-html-editor'].forEach(id => {
            $(id)?.addEventListener('input', debouncedSave);
        });

        const list = $('selected-items-list');
        if (list && 'MutationObserver' in window) {
            new MutationObserver(debouncedSave).observe(list, { childList: true, subtree: true });
        }
    });

    window.addEventListener('beforeunload', function (e) {
        if (dirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
})();
