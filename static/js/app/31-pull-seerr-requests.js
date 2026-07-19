document.getElementById('pullSeerrRequestsBtn').addEventListener('click', async (e) => {
    if (!confirmFreshRepull(e.currentTarget, 'seerr')) return;
    showSpinner('Pulling Seerr requests...', 'seerr_requests');

    const payload = {
        stats: statsList,
        user_dict: userDict,
        graph_data: graphDataList,
        graph_commands: graphCommands,
        recent_data: recentPayload,
        libs: APP.libs,
        settings: APP.settings
    };

    try {
        const resp = await fetch('/pull_seerr_requests', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/html',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(payload),
            credentials: 'same-origin'
        });

        if (!resp.ok) throw new Error('Error pulling Seerr requests.');

        const html = await resp.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');

        const oldCacheCard = document.getElementById('cache-card');
        const newCacheCard = doc.getElementById('cache-card');
        if (oldCacheCard && newCacheCard) oldCacheCard.replaceWith(newCacheCard);

        const oldSeerrRequestsCol = document.getElementById('seerr-requests-col');
        const newSeerrRequestsCol = doc.getElementById('seerr-requests-col');
        if (oldSeerrRequestsCol && newSeerrRequestsCol) oldSeerrRequestsCol.replaceWith(newSeerrRequestsCol);

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

        const oldSeerrData = document.getElementById('seerr-requests-json');
        const newSeerrData = doc.getElementById('seerr-requests-json');
        if (newSeerrData && oldSeerrData) oldSeerrData.replaceWith(newSeerrData);

        buildSeerrRequestsRow();
        markPullCacheFresh('seerr', true);
    } catch (err) {
        console.error("Error pulling Seerr requests:", err);
        const error_p = document.getElementById('error_p');
        if (error_p) error_p.textContent = err;
        alert("Something went wrong while pulling Seerr requests.");
    } finally {
        try { hideSpinner(); } catch(_) {}
    }
});
