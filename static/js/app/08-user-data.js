function readJSONFromScript(id) {
    const el = document.getElementById(id);
    if (!el) return {};
    try {
        const txt = (el.textContent || '').trim();
        if (!txt) return {};
        return JSON.parse(txt);
    } catch (e) {
        console.error(`Invalid JSON in #${id}`, e);
        return {};
    }
}

let recsPayload = readJSONFromScript('recommendations-json');
let droppedneedleWrappedPayload = readJSONFromScript('droppedneedle-wrapped-json');
let droppedneedleServerPayload = readJSONFromScript('droppedneedle-server-json');
let yearlyWrappedPayload = readJSONFromScript('yearly-wrapped-json');
let sonarrComingSoonPayload = readJSONFromScript('sonarr-coming-soon-json');
let radarrComingSoonPayload = readJSONFromScript('radarr-coming-soon-json');
let userDict = APP.userDict || {};

let usersFullData = APP.usersFullData;
const displayPreference = APP.displayPreference;

function getUserDisplayName(userKey) {
    if (!usersFullData || !Array.isArray(usersFullData)) {
        return userDict[userKey] || userKey;
    }
    const user = usersFullData.find(u => String(u.user_id) === String(userKey));
    
    if (!user) {
        return userDict[userKey] || userKey;
    }

    if (displayPreference === 'username') {
        return user.username || user.email || userKey;
    } else if (displayPreference === 'friendly_name') {
        return user.friendly_name || user.username || user.email || userKey;
    } else {
        return user.email || user.username || userKey;
    }
}

// Recipient chips carry the email as identity (data-email) but show a label
// per the Recipient Display Name setting (email / username / friendly_name).
function getEmailDisplayLabel(email) {
    if (!email) return email;
    const key = String(email).toLowerCase();
    if (usersFullData && Array.isArray(usersFullData)) {
        const user = usersFullData.find(u => (u.email || '').toLowerCase() === key);
        if (user) {
            if (displayPreference === 'username') {
                return user.username || user.email || email;
            } else if (displayPreference === 'friendly_name') {
                return user.friendly_name || user.username || user.email || email;
            }
        }
    }
    return email;
}
window.getEmailDisplayLabel = getEmailDisplayLabel;

// Alphabetical sort by the displayed label, so the recipient list matches
// whatever value is shown.
function sortEmailsByLabel(emails) {
    return [...emails].sort((a, b) =>
        getEmailDisplayLabel(a).localeCompare(getEmailDisplayLabel(b), undefined, { sensitivity: 'base' })
    );
}
window.sortEmailsByLabel = sortEmailsByLabel;
