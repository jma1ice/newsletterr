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
        li.className = "group rounded-2xl overflow-hidden bg-[#8acbd4] dark:bg-[#333] ";
        li.innerHTML = `
            <div class="relative aspect-[2/3] bg-gray-200 dark:bg-gray-700">
            ${imgURL ? `<img loading="lazy" src="${imgURL}" class="h-full w-full object-cover">` : ''}
            ${it.library ? `<div class="ra-pill absolute top-1 right-1 text-xs px-2 py-1 rounded-full bg-black/70 text-white"><span class="pill_text">${it.library}</span></div>` : ''}
            ${it.added ? `<div class="ra-pill absolute bottom-1 right-1 text-[11px] text-white/90"><span class="bg-black/60 rounded px-1.5 py-0.5"><span class="pill_text">${it.added}</span></span></div>` : ''}
            </div>
            <div class="p-3">
            <div class="font-semibold line-clamp-2 text-[#333] dark:text-[#8acbd4]">${it.title}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400">${it.sub ? it.sub + ' • ' : ''}${it.duration}</div>
            ${it.summary ? `<div class="mt-2 text-xs text-gray-600 dark:text-gray-300 line-clamp-5">${it.summary}</div>` : ''}
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
                    <button hidden type="button" class="btn button-outline btn-sm me-1 ra-view-btn" 
                            data-lib="${lib}" data-target="${id}" style="font-size: .8rem; padding: .25rem .5rem;">
                    View
                    </button>
                    <button type="button" class="btn button btn-sm ra-add-btn" 
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

    host.innerHTML = statsList.map((stat, index) => `
        <div class="col-12 mb-2">
            <div class="d-flex justify-content-between align-items-center p-2 border rounded">
                <span style="font-size: 0.9rem;">${stat.stat_title}</span>
                <div>
                    <button hidden type="button" class="btn button-outline btn-sm me-1 view-stat-btn"
                            data-target="stat-${index}" style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
                        View
                    </button>
                    <button type="button" class="btn button btn-sm add-stat-btn"
                            data-id="stat-${index}"
                            data-name="${stat.stat_title}"
                            data-type="stat" style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
                        Add
                    </button>
                </div>
            </div>
        </div>
    `).join('');
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

    host.innerHTML = graphDataList.map((graph, index) => {
        const name = graphCommands[index]?.name || `Graph ${index}`;
        return `
            <div class="col-12 mb-2">
                <div class="d-flex justify-content-between align-items-center p-2 border rounded">
                    <span style="font-size: 0.9rem;">${name}</span>
                    <div>
                        <button hidden type="button" class="btn button-outline btn-sm me-1 view-graph-btn"
                                data-target="graph-${index}" style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
                            View
                        </button>
                        <button type="button" class="btn button btn-sm add-graph-btn"
                                data-id="graph-${index}"
                                data-name="${name}"
                                data-type="graph" style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
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
        li.className = "group rounded-2xl overflow-hidden bg-[#8acbd4] dark:bg-[#333] " + 
        "!shadow-[0_6px_18px_rgba(0, 0, 0, 0.6)] hover:!shadow-[0_10px_28px_rgba(0, 0, 0, 0.6)] " + 
        "dark:!shadow-[0_6px_18px_rgba(74, 127, 130, 0.6)] dark:hover:!shadow-[0_10px_28px_rgba(74, 127, 130, 0.6)]";
        li.dataset.lib = it.library;
        li.innerHTML = `
            <style>
                .ra-pill{ display:inline-flex; align-items:center; justify-content:center; line-height:1; }
            </style>
            <div class="relative aspect-[2/3] bg-gray-200 dark:bg-gray-700">
                ${imgURL ? `<img loading="lazy" src="${imgURL}" class="h-full w-full object-cover">` : ''}
                ${it.library ? `<div class="ra-pill absolute top-1 right-1 text-xs px-2 py-1 rounded-full bg-black/70 text-white"><span class="pill_text">${it.library}</span></div>` : ''}
                ${it.added ? `<div class="ra-pill absolute bottom-1 right-1 text-[11px] text-white/90 bg-black/60 rounded px-1.5 py-0.5"><span class="pill_text">${it.added}</span></div>` : ''}
            </div>
            <div class="p-3">
                <div class="font-semibold line-clamp-2">${it.title}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400">
                    ${it.sub ? it.sub + ' • ' : ''}${it.duration}
                </div>
                ${it.summary ? `<div class="mt-2 text-xs text-gray-600 dark:text-gray-300 line-clamp-5">${it.summary}</div>` : ''}
            </div>
        `;
        grid.appendChild(li);
    });
    empty.classList.toggle('hidden', list.length !== 0);
}
