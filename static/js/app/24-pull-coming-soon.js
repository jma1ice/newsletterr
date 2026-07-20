window.pullRunners = window.pullRunners || {};
window.pullRunners.coming_soon = async function ({ chained = false } = {}) {
    showSpinner('Pulling coming soon calendar...', 'coming_soon');

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
        const resp = await fetch('/pull_coming_soon', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/html',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify(payload),
            credentials: 'same-origin'
        });

        if (!resp.ok) throw new Error('Error pulling coming soon calendar.');

        const html = await resp.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');

        const oldCacheCard = document.getElementById('cache-card');
        const newCacheCard = doc.getElementById('cache-card');
        if (oldCacheCard && newCacheCard) oldCacheCard.replaceWith(newCacheCard);

        const oldComingSoonCol = document.getElementById('coming-soon-col');
        const newComingSoonCol = doc.getElementById('coming-soon-col');
        if (oldComingSoonCol && newComingSoonCol) oldComingSoonCol.replaceWith(newComingSoonCol);

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

        const oldSonarrData = document.getElementById('sonarr-coming-soon-json');
        const newSonarrData = doc.getElementById('sonarr-coming-soon-json');
        if (newSonarrData && oldSonarrData) oldSonarrData.replaceWith(newSonarrData);

        const oldRadarrData = document.getElementById('radarr-coming-soon-json');
        const newRadarrData = doc.getElementById('radarr-coming-soon-json');
        if (newRadarrData && oldRadarrData) oldRadarrData.replaceWith(newRadarrData);

        buildSonarrComingSoonRow();
        buildRadarrComingSoonRow();
        markPullCacheFresh('coming_soon', true);
        return { ok: true };
    } catch (err) {
        console.error("Error pulling coming soon calendar:", err);
        const error_p = document.getElementById('error_p');
        if (error_p) error_p.textContent = err;
        if (!chained) alert("Something went wrong while pulling the coming soon calendar.");
        return { ok: false, error: String((err && err.message) || err) };
    } finally {
        try { hideSpinner(); } catch(_) {}
    }
};

document.getElementById('pullComingSoonBtn').addEventListener('click', (e) => {
    if (!confirmFreshRepull(e.currentTarget, 'coming_soon')) return;
    window.pullRunners.coming_soon({ chained: false });
});
