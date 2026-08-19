(function () {
    if (!window.APP || !APP.demo) return;

    const $ = (id) => document.getElementById(id);

    function clickAdds(selector, limit) {
        const buttons = Array.from(document.querySelectorAll(selector)).filter(b => !b.disabled);
        buttons.slice(0, limit).forEach(b => b.click());
    }

    // Recently added has one Add per library and the rows are alphabetical, so
    // "the first two" would pick Movies and Music. Name the two we want.
    function clickRecentlyAdded(preferred) {
        const buttons = Array.from(document.querySelectorAll('.ra-add-btn')).filter(b => !b.disabled);
        const wanted = buttons.filter(b => preferred.includes((b.dataset.lib || '').toLowerCase()));
        (wanted.length ? wanted : buttons.slice(0, 2)).forEach(b => b.click());
    }

    function prefill() {
        if (typeof selectedItems === 'undefined' || selectedItems.length) return;
        if ($('custom-html-editor') && $('custom-html-editor').value.trim()) return;
        if ($('custom-html-toggle') && $('custom-html-toggle').checked) return;

        if ($('subject') && !$('subject').value) {
            $('subject').value = 'This month on the Demo Media Server';
        }
        if ($('email_header_title') && !$('email_header_title').value) {
            $('email_header_title').value = 'What landed this month';
        }

        // Recipients: the demo sample users. Sends are blocked server side, but
        // the recipient-driven snap-ins (recommendations, wrapped) need chips
        // before their pull buttons will run.
        if (window.chipsAddTokens && !document.querySelectorAll('#bcc_chips .nl-chip').length) {
            const emails = Object.values(APP.userDict || {}).slice(0, 2).join(', ');
            if (emails) window.chipsAddTokens(emails);
        }

        $('add-intro-btn')?.click();
        clickRecentlyAdded(['movies', 'tv shows']);
        clickAdds('.add-stat-btn', 1);
        clickAdds('.add-graph-btn', 1);
        clickAdds('.recs-add-btn', 1);
        clickAdds('.sonarr-coming-soon-add-btn', 1);
        clickAdds('.radarr-coming-soon-add-btn', 1);
        $('add-outro-btn')?.click();

        if (typeof updateSelectedItemsDisplay === 'function') updateSelectedItemsDisplay();
        if (typeof updatePreview === 'function') updatePreview();
        // The prefill is the starting point, not unsaved work: no "restore your
        // draft?" prompt on the next visit because of it.
        if (typeof window.markDraftClean === 'function') window.markDraftClean();
        if (typeof window.clearDraft === 'function') window.clearDraft();
    }

    document.addEventListener('DOMContentLoaded', function () {
        // one tick after the other bootstrap handlers, which is what renders the
        // snap-in rows whose Add buttons this clicks
        setTimeout(prefill, 0);
    });
})();
