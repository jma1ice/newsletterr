document.getElementById('pullOmbiRequestsBtn').addEventListener('click', async () => {
    showSpinner('Pulling Ombi requests...');

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
        const resp = await fetch('/pull_ombi_requests', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/html',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(payload),
            credentials: 'same-origin'
        });

        if (!resp.ok) throw new Error('Error pulling Ombi requests.');

        const html = await resp.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');

        const oldCacheCard = document.getElementById('cache-card');
        const newCacheCard = doc.getElementById('cache-card');
        if (oldCacheCard && newCacheCard) oldCacheCard.replaceWith(newCacheCard);

        const oldOmbiRequestsCol = document.getElementById('ombi-requests-col');
        const newOmbiRequestsCol = doc.getElementById('ombi-requests-col');
        if (oldOmbiRequestsCol && newOmbiRequestsCol) oldOmbiRequestsCol.replaceWith(newOmbiRequestsCol);

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

        const oldOmbiData = document.getElementById('ombi-requests-json');
        const newOmbiData = doc.getElementById('ombi-requests-json');
        if (newOmbiData && oldOmbiData) oldOmbiData.replaceWith(newOmbiData);

        buildOmbiRequestsRow();
    } catch (err) {
        console.error("Error pulling Ombi requests:", err);
        const error_p = document.getElementById('error_p');
        if (error_p) error_p.textContent = err;
        alert("Something went wrong while pulling Ombi requests.");
    } finally {
        try { hideSpinner(); } catch(_) {}
    }
});
