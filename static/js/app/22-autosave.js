(function () {
    const KEY = 'newsletterr_draft';
    let dirty = false;
    let restoring = false;

    const $ = (id) => document.getElementById(id);

    function snapshot() {
        return {
            subject: $('subject')?.value || '',
            header: $('email_header_title')?.value || '',
            customHtml: $('custom-html-editor')?.value || '',
            items: (typeof selectedItems !== 'undefined') ? selectedItems : [],
            ts: Date.now(),
        };
    }

    function saveDraft() {
        if (restoring) return;
        try {
            const snap = snapshot();
            const hasContent = snap.subject || snap.header || (snap.items && snap.items.length);
            if (!hasContent) return;
            localStorage.setItem(KEY, JSON.stringify(snap));
            dirty = true;
        } catch (e) {
            /* storage full or unavailable: ignore */
        }
    }

    const debouncedSave = (typeof debounce === 'function') ? debounce(saveDraft, 500) : saveDraft;

    window.clearDraft = function () {
        try { localStorage.removeItem(KEY); } catch (e) {}
        dirty = false;
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
            && !($('subject')?.value) && !($('email_header_title')?.value);
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
