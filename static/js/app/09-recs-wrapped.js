function posterCard(p, faded=false) {
    const src = p.url ? `/proxy-img?u=${encodeURIComponent(p.url)}` : '';
    const title = p.title || '';
    const runtime = p.runtime || '';
    const y = p.year ? String(p.year) : '';
    const vote = typeof p.vote === 'number'
                        ? String((Math.round(p.vote * 10) / 10)).replace(/\.0$/,'')
                        : '';
    const bits = [y, vote ? `★ ${vote}` : ''].filter(Boolean).join(' • ');
    const ov = p.overview || '';

    return `
        <li class="relative group rounded-3 overflow-hidden bg-gray-200 dark:bg-gray-700 text-white">
            <a href="${p.href || '#'}" target="_blank" rel="noopener" class="block text-white">
                <div class="aspect-[2/3]">
                    ${src ? `<img loading="eager" src="${src}" class="h-full w-full object-cover">` : ''}
                </div>

                <div class="absolute top-1 left-1 text-[11px] text-white/90">
                    ${bits ? `<span class="bg-black/70 rounded px-1.5 py-0.5 text-white"><span class="text-white pill_text">${bits}</span></span>` : ''}
                </div>

                ${faded ? `
                    <div class="absolute top-6 left-1 text-[10px] bg-rose-600/85 text-white rounded px-1.5 py-0.5">
                        <span class="text-white pill_text">Unavailable</span>
                    </div>` : ''}

                <div class="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/70 to-transparent">
                    <div class="text-[12px] font-semibold text-white line-clamp-2">${title}</div>
                    ${runtime ? `<div class="text-[11px] text-white/80">${runtime}</div>` : ''}
                </div>
            </a>

            ${ov ? `
                <div class="absolute left-0 right-0 bottom-0 translate-y-full group-hover:translate-y-0 transition
                        text-[10px] bg-black/80 text-white px-2 py-1 line-clamp-3">${ov}</div>` : ''}
        </li>`;
}

function buildRecsBlockForUser(userKey, { headingTag = 'h4' } = {}, { bgColorway = 'view' } = {}) {
    const COLUMNS = 5;

    recsPayload = readJSONFromScript('recommendations-json');
    const data = recsPayload[userKey] || {};
    const moviesAvail = data.movie_posters || [];
    const moviesUn = data.movie_posters_unavailable || [];
    const showsAvail = data.show_posters || [];
    const showsUn = data.show_posters_unavailable || [];

    const wrap = document.createElement('div');
    if (bgColorway === 'view') {
        wrap.className = "rec-user-card rounded-3 bg-[#8acbd4] dark:bg-[#333] relative !shadow-none";
    } else {
        wrap.className = "rec-user-card rounded-3 bg-[#282A2D] relative !shadow-none";
    }

    const section = (label) => {
        const h = document.createElement(headingTag);
        h.textContent = label;
        if (bgColorway === 'view') {
            h.classList.add('text-[#333]');
            h.classList.add('dark:text-[#8acbd4]');
        } else {
            h.classList.add('text-[#8acbd4]');
            h.classList.add('!important');
        }
        h.classList.add('pb-4')
        wrap.appendChild(h);
    };

    const grid = () => {
        const ul = document.createElement('ul');
        ul.className = "grid grid-cols-5 gap-3";
        ul.style.display = 'grid';
        ul.style.gridTemplateColumns = `repeat(${COLUMNS}, minmax(0, 1fr))`;
        ul.style.gap = '12px';
        ul.style.listStyle = 'none';
        ul.style.padding = '0';
        ul.style.margin = '0';
        return ul;
    };

    const appendPosters = (ul, arr, faded=false) => {
        ul.insertAdjacentHTML('beforeend', arr.map(p => posterCard(p, faded)).join(''));
    };

    const firstSpan = (availLen) => {
        const remainder = (COLUMNS - (availLen % COLUMNS)) % COLUMNS;
        return remainder !== 0 ? remainder : COLUMNS;
    };

    const clampGap = (span) => {
        if (span <= 1) return '0.75rem';
        const v = span / (span - 1.5);
        return (Math.max(0.5, Math.min(2.0, v))).toFixed(2) + 'rem';
    };

    const makeUnavailableRows = (unArr, span) => {
        const frag = document.createDocumentFragment();
        const firstRow = unArr.slice(0, span);
        const rest = unArr.slice(span);

        if (firstRow.length) {
            const li = document.createElement('li');
            li.className = "col-span-full";
            li.style.gridColumn = `span ${span} / span ${span}`;
            const box = document.createElement('div');
            box.className = "relative rounded";
            const ring = document.createElement('div');
            ring.className = "pointer-events-none absolute inset-0 rounded";
            ring.style.boxShadow = '0 0 0 1px #f59e0b inset';
            const ul = document.createElement('ul');
            ul.className = "grid p-1";
            ul.style.display = 'grid';
            ul.style.gridTemplateColumns = `repeat(${span}, minmax(0, 1fr))`;
            ul.style.gap = clampGap(span);
            firstRow.forEach(p => ul.insertAdjacentHTML('beforeend', posterCard(p, true)));
            box.appendChild(ring);
            box.appendChild(ul);
            li.appendChild(box);
            frag.appendChild(li);
        }

        for (let i=0; i<rest.length; i+=COLUMNS) {
            const chunk = rest.slice(i, i+COLUMNS);
            const li = document.createElement('li');
            li.className = "col-span-full";
            const box = document.createElement('div');
            box.className = "relative rounded";
            const ring = document.createElement('div');
            ring.className = "pointer-events-none absolute inset-0 rounded";
            ring.style.boxShadow = '0 0 0 1px #f59e0b inset';
            const ul = document.createElement('ul');
            ul.className = "grid p-1";
            ul.style.display = 'grid';
            ul.style.gridTemplateColumns = `repeat(${COLUMNS}, minmax(0, 1fr))`;
            ul.style.gap = '0.75rem';
            chunk.forEach(p => { if (p) ul.insertAdjacentHTML('beforeend', posterCard(p, true)); });
            box.appendChild(ring);
            box.appendChild(ul);
            li.appendChild(box);
            frag.appendChild(li);
        }

        return frag;
    };

    if (moviesAvail.length || moviesUn.length) {
        section("Recommended Movies");
        const ul = grid();
        appendPosters(ul, moviesAvail, false);
        if (moviesUn.length) ul.appendChild(makeUnavailableRows(moviesUn, firstSpan(moviesAvail.length)));
        wrap.appendChild(ul);
    }

    if (showsAvail.length || showsUn.length) {
        section("Recommended Shows");
        const ul = grid();
        appendPosters(ul, showsAvail, false);
        if (showsUn.length) ul.appendChild(makeUnavailableRows(showsUn, firstSpan(showsAvail.length)));
        wrap.appendChild(ul);
    }

    return wrap;
}

function buildRecsUserRows() {
    recsPayload = readJSONFromScript('recommendations-json');
    const host = document.getElementById('recs-user-list');
    if (!host) return;

    const users = Object.keys(recsPayload || {}).filter(Boolean).sort();

    users.forEach(userKey => {
        const display = userDict[userKey] || userKey;
        const id = `recs-user-${slug(display)}`;

        const row = document.createElement('div');
        row.className = 'col-12 mb-2';
        row.innerHTML = `
            <div class="d-flex justify-content-between align-items-center p-2 border rounded">
                <span style="font-size: .9rem;">${display}</span>
                <div>
                    <button hidden type="button"
                            class="btn button-outline btn-sm me-1 recs-view-btn"
                            data-user-key="${userKey}" data-target="${id}"
                            style="font-size: .8rem; padding: .25rem .5rem;">View</button>
                    <button type="button"
                            class="btn button btn-sm recs-add-btn"
                            data-type="recommendations" data-id="${id}"
                            data-name="Recommendations: ${display}"
                            data-user-key="${userKey}"
                            style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
                </div>
            </div>`;
        host.appendChild(row);
    });
};
buildRecsUserRows();

function buildWrappedUserRows() {
    droppedneedleWrappedPayload = readJSONFromScript('droppedneedle-wrapped-json');
    const host = document.getElementById('droppedneedle-user-list');
    if (!host) return;
    host.innerHTML = '';

    const users = Object.keys(droppedneedleWrappedPayload || {}).filter(Boolean).sort();

    users.forEach(userKey => {
        const display = userDict[userKey] || userKey;
        const id = `droppedneedle-user-${slug(display)}`;

        const row = document.createElement('div');
        row.className = 'col-12 mb-2';
        row.innerHTML = `
            <div class="d-flex justify-content-between align-items-center p-2 border rounded">
                <span style="font-size: .9rem;">${display}</span>
                <div>
                    <button type="button"
                            class="btn button btn-sm droppedneedle-add-btn"
                            data-type="droppedneedle_wrapped" data-id="${id}"
                            data-name="Wrapped: ${display}"
                            data-user-key="${userKey}"
                            style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
                </div>
            </div>`;
        host.appendChild(row);
    });
};
buildWrappedUserRows();

function buildDroppedNeedleServerRow() {
    droppedneedleServerPayload = readJSONFromScript('droppedneedle-server-json');
    const host = document.getElementById('droppedneedle-server-list');
    if (!host) return;
    host.innerHTML = '';
    if (!droppedneedleServerPayload) return;

    const row = document.createElement('div');
    row.className = 'col-12 mb-2';
    row.innerHTML = `
        <div class="d-flex justify-content-between align-items-center p-2 border rounded">
            <span style="font-size: .9rem;">Server Stats (${droppedneedleServerPayload.year || ''})</span>
            <div>
                <button type="button"
                        class="btn button btn-sm droppedneedle-server-add-btn"
                        data-type="droppedneedle_server_stats" data-id="droppedneedle-server-stats"
                        data-name="DroppedNeedle Server Stats"
                        style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
            </div>
        </div>`;
    host.appendChild(row);
};
buildDroppedNeedleServerRow();
