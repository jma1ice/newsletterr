// Escapes text for safe interpolation into innerHTML template literals.
// Use on any server-supplied or metadata-derived string (titles, summaries,
// library and user names) before it lands in markup.
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
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
