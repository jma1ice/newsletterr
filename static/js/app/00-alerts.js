// Escapes text for safe interpolation into innerHTML template literals.
// Use on any server-supplied or metadata-derived string (titles, summaries,
// library and user names) before it lands in markup.
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// Two-click guard for the pull buttons: when the data behind a button is
// already fresh in the cache (APP.pullCacheFresh, updated after each pull),
// the first click swaps the button label into a confirmation and returns
// false; a second click within the timeout proceeds. Returns true when the
// pull should run.
function confirmFreshRepull(btn, key) {
    if (!btn || !window.APP?.pullCacheFresh?.[key]) return true;
    if (btn.dataset.repullArmed === '1') {
        clearTimeout(Number(btn.dataset.repullTimer));
        btn.textContent = btn.dataset.repullLabel;
        delete btn.dataset.repullArmed;
        return true;
    }
    btn.dataset.repullArmed = '1';
    btn.dataset.repullLabel = btn.textContent;
    btn.textContent = 'Data is fresh, click again to re-pull';
    btn.dataset.repullTimer = String(setTimeout(() => {
        btn.textContent = btn.dataset.repullLabel;
        delete btn.dataset.repullArmed;
    }, 4000));
    return false;
}

function markPullCacheFresh(key, value) {
    if (window.APP?.pullCacheFresh) window.APP.pullCacheFresh[key] = value;
}

(function() {
    const a = document.getElementById('alert_p');
    const e = document.getElementById('error_p');
    if (a && a.textContent.trim()) a.style.display = '';
    if (e && e.textContent.trim()) e.style.display = '';

    const plexClose = document.getElementById('plex_warning_close');
    if (plexClose) {
        plexClose.addEventListener('click', () => {
            const banner = document.getElementById('plex_warning_p');
            if (banner) banner.style.display = 'none';
        });
    }
})();
