window.pullRunners = window.pullRunners || {};
window.pullRunners.droppedneedle = async function ({ chained = false } = {}) {
    showSpinner('Pulling DroppedNeedle stats...');

    function collectEmailsFromChips() {
        return Array.from(document.querySelectorAll('#bcc_chips .nl-chip'))
            .map(ch => ch.dataset.email)
            .filter(Boolean);
    }

    const chipInput = document.getElementById('email_chip_input');
        if (chipInput && chipInput.value.trim()) {
            chipInput.dispatchEvent(new Event('blur'));
    }

    const toList = collectEmailsFromChips();
        if (!toList.length) {
            try { hideSpinner(); } catch(_) {}
            if (!chained) alert('Please add at least one recipient.');
            return { ok: false, error: 'No recipients' };
    }

    const to_emails = toList.join(', ');

    const payload = {
        stats: statsList,
        user_dict: userDict,
        graph_data: graphDataList,
        graph_commands: graphCommands,
        recent_data: recentPayload,
        libs: APP.libs,
        settings: APP.settings,
        to_emails
    };

    try {
        const resp = await fetch('/pull_droppedneedle_stats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/html',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(payload),
            credentials: 'same-origin'
        });

        if (!resp.ok) throw new Error('Error pulling DroppedNeedle stats.');

        const html = await resp.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');

        const oldCacheCard = document.getElementById('cache-card');
        const newCacheCard = doc.getElementById('cache-card');
        oldCacheCard.replaceWith(newCacheCard);

        const oldMsCol = document.getElementById('droppedneedle-col');
        const newMsCol = doc.getElementById('droppedneedle-col');
        oldMsCol.replaceWith(newMsCol);

        const oldMsPreview = document.getElementById('droppedneedle-preview');
        const newMsPreview = doc.getElementById('droppedneedle-preview');
        oldMsPreview.replaceWith(newMsPreview);

        const oldAlertP = document.getElementById('alert_p');
        const newAlertP = doc.getElementById('alert_p');
        if (oldAlertP && newAlertP) {
            newAlertP.style.display = newAlertP.textContent.trim() ? '' : 'none';
            oldAlertP.replaceWith(newAlertP);
        }

        const oldErrorP = document.getElementById('error_p');
        const newErrorP = doc.getElementById('error_p');
        if (oldErrorP && newErrorP) {
            newErrorP.style.display = newErrorP.textContent.trim() ? '' : 'none';
            oldErrorP.replaceWith(newErrorP);
        }

        const oldWrappedData = document.getElementById('droppedneedle-wrapped-json');
        const newWrappedData = doc.getElementById('droppedneedle-wrapped-json');
        if (newWrappedData && oldWrappedData) oldWrappedData.replaceWith(newWrappedData);

        const oldServerData = document.getElementById('droppedneedle-server-json');
        const newServerData = doc.getElementById('droppedneedle-server-json');
        if (newServerData && oldServerData) oldServerData.replaceWith(newServerData);

        buildWrappedUserRows();
        buildDroppedNeedleServerRow();
        markPullCacheFresh('droppedneedle', true);
        return { ok: true };
    } catch (err) {
        console.error("Error pulling DroppedNeedle stats:", err);
        const error_p = document.getElementById('error_p');
        error_p.textContent = err;
        if (!chained) alert("Something went wrong while pulling DroppedNeedle stats.");
        return { ok: false, error: String((err && err.message) || err) };
    } finally {
        try { hideSpinner(); } catch(_) {}
    }
};

document.getElementById('pullDroppedNeedleBtn').addEventListener('click', (e) => {
    if (!confirmFreshRepull(e.currentTarget, 'droppedneedle')) return;
    window.pullRunners.droppedneedle({ chained: false });
});
