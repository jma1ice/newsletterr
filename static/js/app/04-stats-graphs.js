let selectedItems = [];
const hideGraphPlayCounts = APP.hideGraphPlayCounts;
const statType = APP.statType;
const recentlyAddedMode = APP.recentlyAddedMode;
const raGridColumns = parseInt(APP.raGridColumns) || 5;
const recsGridColumns = parseInt(APP.recsGridColumns) || 5;
const showStatCoverArt = APP.statCoverArt === "enabled";
const _defaultIntroText = APP.defaultIntroText || '';
const _defaultOutroText = APP.defaultOutroText || '';
const _serverNameForDefaults = APP.serverName;
const _resolvedIntroDefault = _defaultIntroText || `You are receiving this email because you are a member of ${_serverNameForDefaults}.`;
const _resolvedOutroDefault = _defaultOutroText || 'Thanks for using Plex and for reading this newsletterr email!';
let statsList = [];
try {
    statsList = APP.statsList;
} catch (e) {
    statsList = [];
    console.error("Error parsing stats:", e);
}

document.addEventListener('DOMContentLoaded', () => {
    const frame = document.getElementById('preview');
    if (frame) {
        // A neutral loading state until the first server render returns. The
        // real preview POST to /preview_email can take a moment on a cold load,
        // so show something intentional rather than a leftover debug message.
        frame.srcdoc = '<html><body style="margin:0;font-family:system-ui,sans-serif;color:#888;display:flex;align-items:center;justify-content:center;height:100vh;"><p>Loading preview&hellip;</p></body></html>';
    }

    setTimeout(() => {
        updatePreview();
    }, 100);
});

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('email_header_title').addEventListener('input', debouncedUpdatePreview);
});
