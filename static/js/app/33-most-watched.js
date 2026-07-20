// Most Watched snap-in (NEWS-17): per-library rows like the Recently Added
// list, built from the cached most_watched_data pulled during /pull_stats.
// Each row has the optional per-library count input (the raCount pattern).
let mostWatchedPayload = APP.mostWatchedPayload || [];

function buildMWLibraryRows() {
    const host = document.getElementById('mw-lib-list');
    if (!host) return;

    const items = mostWatchedPayload.flatMap(x => x?.most_watched || []);
    const libs = [...new Set(items.map(i => i.library_name).filter(Boolean))].sort();
    host.innerHTML = '';

    libs.forEach(lib => {
        const row = document.createElement('div');
        row.className = 'col-12 mb-2';
        const id = `mw-lib-${slug(lib)}`;

        row.innerHTML = `
            <div class="snapin-row p-2 border rounded">
                <div class="snapin-row-actions">
                    <button type="button" class="nl-btn nl-btn--primary nl-btn--sm mw-add-btn"
                            data-type="most_watched" data-lib="${escapeHtml(lib)}" data-id="${id}" data-name="Most Watched: ${escapeHtml(lib)}"
                            style="font-size: .8rem; padding: .25rem .5rem;">
                    Add
                    </button>
                </div>
                <span class="snapin-row-label" title="${escapeHtml(lib)}">${escapeHtml(lib)}</span>
                <select class="mw-scope-select"
                        title="Time scope for ${escapeHtml(lib)}: all-time play counts, or plays within the pulled time range. Set before clicking Add."
                        style="width: 8em; margin-left: auto; flex-shrink: 0; font-size: .8rem; padding: .15rem .3rem;">
                    <option value="">All-time</option>
                    <option value="recent">Pull range</option>
                </select>
                <input type="number" class="mw-count-input" min="1" max="25" placeholder="10"
                       title="Max items shown for ${escapeHtml(lib)} (blank = 10). Set before clicking Add."
                       style="width: 4em; flex-shrink: 0; font-size: .8rem; padding: .15rem .3rem;">
            </div>`;
        host.appendChild(row);
    });
}

document.addEventListener('DOMContentLoaded', buildMWLibraryRows);
