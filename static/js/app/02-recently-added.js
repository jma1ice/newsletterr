let recentPayload = APP.recentPayload;
const renderedCharts = new Set();
let graphDataList = APP.graphDataList;
let graphCommands = APP.graphCommands;
const themeSettings = (() => {
    try {
        return APP.themeSettings;
    } catch (e) {
        console.error("Error parsing theme settings:", e);
        return {};
    }
})();

function buildThumb(path) {
    if (!path) return '';
    const p = path.startsWith('/') ? path : '/' + path;
    return `/proxy-art${p}`;
}

function pickThumb(it) {
    const type = (it.media_type || it.type || '').toLowerCase();

    const candidates = (type === 'episode' || type === 'season')
        ? [it.grandparent_thumb, it.parent_thumb, it.thumb, it.art]
        : [it.thumb, it.art, it.parent_thumb, it.grandparent_thumb];

    return candidates.find(Boolean) || '';
}

const flatten = (arr) => arr.flatMap(x => x?.recently_added || []);
const msToHMS = (ms) => {
    ms = parseInt(ms || 0, 10);
    const s = Math.round(ms / 1000);
    const h = Math.floor(s/3600), m = Math.floor((s%3600)/60);
    return h ? `${h}h ${m}m` : `${m}m`;
};

const formatDate = (d) => {
    if (!d) return '';
    
    let targetDate;
    if (/^\d+$/.test(String(d))) {
        targetDate = new Date(parseInt(d, 10) * 1000);
    } else {
        targetDate = new Date(d);
    }
    
    if (isNaN(targetDate)) return '';
    
    const now = new Date();
    const diffMs = now - targetDate;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffDays < 0) {
        return `in ${Math.abs(diffDays)} days`;
    } else if (diffDays === 0) {
        return 'today';
    } else if (diffDays === 1) {
        return 'yesterday';
    } else {
        return `${diffDays} days ago`;
    }
};

function buildItemsFromPayload() {
    return flatten(recentPayload).map(it => {
        const title = it.title || it.full_title || it.parent_title || it.grandparent_title || '(untitled)';
        const sub = it.year || it.grandparent_title || it.parent_title || '';
        const thumbPath = pickThumb(it);

        const item_type = (it.media_type || it.type || '').toLowerCase();
        let summary = '';
        if (item_type === 'episode' || item_type === 'season') {
            summary = it.grandparent_tagline || it.grandparent_summary || it.parent_summary || it.tagline || it.summary || '';
        } else {
            summary = it.tagline || it.summary || '';
        }

        return {
            library: it.library_name || it.section_name || it.media_type || '',
            title,
            sub,
            summary: summary,
            duration: msToHMS(it.duration),
            added: formatDate(it.updated_at || it.originally_available_at),
            thumb: thumbPath,
            content_rating: it.content_rating || ''
        };
    });
}
let items = buildItemsFromPayload();

const slug = s => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/(^-|-$)/g,'');

function renderRAGrid(list, target) {
    target.innerHTML = '';
    list.forEach(it => {
        const imgURL = it.thumb ? `/proxy-art${it.thumb.startsWith('/')?it.thumb:('/'+it.thumb)}` : '';
        const li = document.createElement('li');
        li.className = "ra-card";
        li.innerHTML = `
            <div class="ra-card-imgwrap">
            ${imgURL ? `<img loading="lazy" src="${imgURL}">` : ''}
            ${it.library ? `<div class="ra-pill ra-pill--lib"><span class="pill_text">${it.library}</span></div>` : ''}
            ${it.added ? `<div class="ra-pill ra-pill--added"><span class="pill_text">${it.added}</span></div>` : ''}
            </div>
            <div class="ra-card-body">
            <div class="ra-card-title">${it.title}</div>
            <div class="ra-card-sub">${it.sub ? it.sub + ' • ' : ''}${it.duration}</div>
            ${it.summary ? `<div class="ra-card-summary">${it.summary}</div>` : ''}
            </div>`;
        target.appendChild(li);
    });
}

function buildRALibraryRows() {
    items = buildItemsFromPayload();
    const libs = [...new Set(items.map(i => i.library).filter(Boolean))].sort();
    const host = document.getElementById('ra-lib-list');
    if (!host) return;
    host.innerHTML = '';

    libs.forEach(lib => {
        const row = document.createElement('div');
        row.className = 'col-12 mb-2';
        const id = `ra-lib-${slug(lib)}`;

        row.innerHTML = `
            <div class="d-flex justify-content-between align-items-center p-2 border rounded">
                <span style="font-size: .9rem;">${lib}</span>
                <div>
                    <button hidden type="button" class="nl-btn nl-btn--ghost nl-btn--sm me-1 ra-view-btn" 
                            data-lib="${lib}" data-target="${id}" style="font-size: .8rem; padding: .25rem .5rem;">
                    View
                    </button>
                    <button type="button" class="nl-btn nl-btn--primary nl-btn--sm ra-add-btn" 
                            data-type="recently added" data-lib="${lib}" data-id="${id}" data-name="Recently Added: ${lib}"
                            style="font-size: .8rem; padding: .25rem .5rem;">
                    Add
                    </button>
                </div>
            </div>`;
        host.appendChild(row);
    });
}

function buildStatsRows() {
    const host = document.getElementById('stats-list');
    if (!host) return;

    const isEmpty = !statsList || statsList.length === 0;

    if (isEmpty) {
        host.innerHTML = `
            <div class="alert alert-info" style="font-size: 0.9rem; padding: 0.75rem;">
                No stats data available. Click <strong>"Get Stats\\Users"</strong> to load data.
            </div>`;
        return;
    }

    const userInfoDisabled = window.APP?.includeUserInfo === 'disabled';
    host.innerHTML = statsList.map((stat, index) => {
        const blocked = userInfoDisabled && stat.stat_title === 'Most Active Users';
        const hint = blocked ? "Hidden because 'Include Other Users' Info' is disabled in Settings" : '';
        return `
        <div class="col-12 mb-2">
            <div class="d-flex justify-content-between align-items-center p-2 border rounded snapin-row${blocked ? ' opacity-50' : ''}"${blocked ? ` title="${hint}"` : ''}>
                <span class="snapin-row-label" title="${blocked ? hint : stat.stat_title}">${stat.stat_title}</span>
                <div class="snapin-row-actions">
                    <button hidden type="button" class="nl-btn nl-btn--ghost nl-btn--sm me-1 view-stat-btn"
                            data-target="stat-${index}" style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
                        View
                    </button>
                    <button type="button" class="nl-btn nl-btn--primary nl-btn--sm add-stat-btn"
                            data-id="stat-${index}"
                            data-name="${stat.stat_title}"
                            data-type="stat"${blocked ? ' disabled title="' + hint + '"' : ''} style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
                        Add
                    </button>
                </div>
            </div>
        </div>
    `;
    }).join('');
}

function buildGraphsRows() {
    const host = document.getElementById('graphs-list');
    if (!host) return;

    const isEmpty = !graphDataList || graphDataList.length === 0 || 
                    JSON.stringify(graphDataList) === JSON.stringify([{}, {}]);

    if (isEmpty) {
        host.innerHTML = `
            <div class="alert alert-info" style="font-size: 0.9rem; padding: 0.75rem;">
                No graph data available. Click <strong>"Get Stats\\Users"</strong> to load data.
            </div>`;
        return;
    }

    const userInfoDisabled = window.APP?.includeUserInfo === 'disabled';
    const userGraphs = new Set(['Plays by Top Users', 'Stream Type by Top Users']);
    host.innerHTML = graphDataList.map((graph, index) => {
        const name = graphCommands[index]?.name || `Graph ${index}`;
        const blocked = userInfoDisabled && userGraphs.has(name);
        const hint = blocked ? "Hidden because 'Include Other Users' Info' is disabled in Settings" : '';
        return `
            <div class="col-12 mb-2">
                <div class="d-flex justify-content-between align-items-center p-2 border rounded snapin-row${blocked ? ' opacity-50' : ''}"${blocked ? ` title="${hint}"` : ''}>
                    <span class="snapin-row-label" title="${blocked ? hint : name}">${name}</span>
                    <div class="snapin-row-actions">
                        <button hidden type="button" class="nl-btn nl-btn--ghost nl-btn--sm me-1 view-graph-btn"
                                data-target="graph-${index}" style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
                            View
                        </button>
                        <button type="button" class="nl-btn nl-btn--primary nl-btn--sm add-graph-btn"
                                data-id="graph-${index}"
                                data-name="${name}"
                                data-type="graph"${blocked ? ' disabled title="' + hint + '"' : ''} style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
                            Add
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
    buildRALibraryRows();
    buildStatsRows();
    buildGraphsRows();
});

const grid = document.getElementById('ra-grid');
const empty = document.getElementById('ra-empty');

function render(list) {
    grid.innerHTML = '';
    list.forEach(it => {
        const imgURL = buildThumb(it.thumb);
        const li = document.createElement('li');
        li.className = "ra-card";
        li.dataset.lib = it.library;
        li.innerHTML = `
            <div class="ra-card-imgwrap">
                ${imgURL ? `<img loading="lazy" src="${imgURL}">` : ''}
                ${it.library ? `<div class="ra-pill ra-pill--lib"><span class="pill_text">${it.library}</span></div>` : ''}
                ${it.added ? `<div class="ra-pill ra-pill--added"><span class="pill_text">${it.added}</span></div>` : ''}
            </div>
            <div class="ra-card-body">
                <div class="ra-card-title">${it.title}</div>
                <div class="ra-card-sub">
                    ${it.sub ? it.sub + ' • ' : ''}${it.duration}
                </div>
                ${it.summary ? `<div class="ra-card-summary">${it.summary}</div>` : ''}
            </div>
        `;
        grid.appendChild(li);
    });
    empty.classList.toggle('hidden', list.length !== 0);
}
