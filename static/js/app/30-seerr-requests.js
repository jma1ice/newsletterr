function buildSeerrRequestsRow() {
    seerrRequestsPayload = readJSONFromScript('seerr-requests-json');
    const host = document.getElementById('seerr-requests-list');
    if (!host) return;
    host.innerHTML = '';
    if (!seerrRequestsPayload) return;

    const row = document.createElement('div');
    row.className = 'col-12 mb-2';
    row.innerHTML = `
        <div class="snapin-row p-2 border rounded">
            <div class="snapin-row-actions">
                <button type="button"
                        class="nl-btn nl-btn--primary nl-btn--sm seerr-requests-add-btn"
                        data-type="seerr_requests" data-id="seerr-requests"
                        data-name="Recent Requests (Seerr)"
                        style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
            </div>
            <span class="snapin-row-label" title="Recent Requests (Seerr)">Recent Requests (Seerr)</span>
        </div>`;
    host.appendChild(row);
};
buildSeerrRequestsRow();
