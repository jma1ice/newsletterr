// Top Viewer snap-in: a callout for whoever streamed the most over
// the pull's time range.
function hasTopViewerStat() {
    const stats = (typeof statsList !== 'undefined' && statsList) || [];
    return stats.some(s => (s?.stat_title || '').trim().toLowerCase() === 'most active users'
        && Array.isArray(s.rows) && s.rows.length > 0);
}

function refreshTopViewerCard() {
    const card = document.getElementById('top-viewer-card');
    if (!card) return;
    card.style.display = hasTopViewerStat() ? '' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    refreshTopViewerCard();

    // the stats pull replaces statsList; re-check once it settles
    const runners = window.pullRunners;
    if (runners && typeof runners.stats === 'function' && !runners.stats.__topViewerHooked) {
        const original = runners.stats;
        const wrapped = async function () {
            try {
                return await original.apply(this, arguments);
            } finally {
                refreshTopViewerCard();
            }
        };
        wrapped.__topViewerHooked = true;
        runners.stats = wrapped;
    }
});
