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
