function buildOmbiRequestsRow() {
    ombiRequestsPayload = readJSONFromScript('ombi-requests-json');
    const host = document.getElementById('ombi-requests-list');
    if (!host) return;
    host.innerHTML = '';
    if (!ombiRequestsPayload) return;

    const row = document.createElement('div');
    row.className = 'col-12 mb-2';
    row.innerHTML = `
        <div class="snapin-row p-2 border rounded">
            <div class="snapin-row-actions">
                <button type="button"
                        class="nl-btn nl-btn--primary nl-btn--sm ombi-requests-add-btn"
                        data-type="ombi_requests" data-id="ombi-requests"
                        data-name="Recent Requests (Ombi)"
                        style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
            </div>
            <span class="snapin-row-label" title="Recent Requests (Ombi)">Recent Requests (Ombi)</span>
        </div>`;
    host.appendChild(row);
};
buildOmbiRequestsRow();
