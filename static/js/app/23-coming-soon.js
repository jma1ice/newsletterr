function buildSonarrComingSoonRow() {
    sonarrComingSoonPayload = readJSONFromScript('sonarr-coming-soon-json');
    const host = document.getElementById('sonarr-coming-soon-list');
    const block = document.getElementById('sonarr-coming-soon-block');
    if (!host) return;
    host.innerHTML = '';
    if (!sonarrComingSoonPayload) {
        if (block) block.style.display = 'none';
        return;
    }
    if (block) block.style.display = '';

    const row = document.createElement('div');
    row.className = 'col-12 mb-2';
    row.innerHTML = `
        <div class="d-flex justify-content-between align-items-center p-2 border rounded">
            <span style="font-size: .9rem;">Coming Soon (TV)</span>
            <div>
                <button type="button"
                        class="nl-btn nl-btn--primary nl-btn--sm sonarr-coming-soon-add-btn"
                        data-type="sonarr_coming_soon" data-id="sonarr-coming-soon"
                        data-name="Coming Soon (TV)"
                        style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
            </div>
        </div>`;
    host.appendChild(row);
};
buildSonarrComingSoonRow();

function buildRadarrComingSoonRow() {
    radarrComingSoonPayload = readJSONFromScript('radarr-coming-soon-json');
    const host = document.getElementById('radarr-coming-soon-list');
    const block = document.getElementById('radarr-coming-soon-block');
    if (!host) return;
    host.innerHTML = '';
    if (!radarrComingSoonPayload) {
        if (block) block.style.display = 'none';
        return;
    }
    if (block) block.style.display = '';

    const row = document.createElement('div');
    row.className = 'col-12 mb-2';
    row.innerHTML = `
        <div class="d-flex justify-content-between align-items-center p-2 border rounded">
            <span style="font-size: .9rem;">Coming Soon (Movies)</span>
            <div>
                <button type="button"
                        class="nl-btn nl-btn--primary nl-btn--sm radarr-coming-soon-add-btn"
                        data-type="radarr_coming_soon" data-id="radarr-coming-soon"
                        data-name="Coming Soon (Movies)"
                        style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
            </div>
        </div>`;
    host.appendChild(row);
};
buildRadarrComingSoonRow();
