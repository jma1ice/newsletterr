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
        <li class="rec-poster">
            <a href="${escapeHtml(p.href || '#')}" target="_blank" rel="noopener">
                <div class="rec-poster-imgwrap">
                    ${src ? `<img loading="eager" src="${escapeHtml(src)}">` : ''}
                </div>

                <div class="rec-poster-meta">
                    ${bits ? `<span class="pill"><span class="pill_text">${escapeHtml(bits)}</span></span>` : ''}
                </div>

                ${faded ? `
                    <div class="rec-poster-unavail">
                        <span class="pill_text">Unavailable</span>
                    </div>` : ''}

                <div class="rec-poster-caption">
                    <div class="rec-poster-title">${escapeHtml(title)}</div>
                    ${runtime ? `<div class="rec-poster-runtime">${escapeHtml(runtime)}</div>` : ''}
                </div>
            </a>

            ${ov ? `
                <div class="rec-poster-overview">${escapeHtml(ov)}</div>` : ''}
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
    wrap.className = "rec-user-card";
    wrap.style.position = 'relative';

    const section = (label) => {
        const h = document.createElement(headingTag);
        h.textContent = label;
        h.style.paddingBottom = 'var(--space-4)';
        wrap.appendChild(h);
    };

    const grid = () => {
        const ul = document.createElement('ul');
        ul.className = "rec-poster-row";
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
            <div class="snapin-row p-2 border rounded">
                <div class="snapin-row-actions">
                    <button type="button"
                            class="nl-btn nl-btn--primary nl-btn--sm recs-add-btn"
                            data-type="recommendations" data-id="${id}"
                            data-name="Recommendations: ${escapeHtml(display)}"
                            data-user-key="${escapeHtml(userKey)}"
                            style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
                </div>
                <span class="snapin-row-label" title="${escapeHtml(display)}">${escapeHtml(display)}</span>
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
            <div class="snapin-row p-2 border rounded">
                <div class="snapin-row-actions">
                    <button type="button"
                            class="nl-btn nl-btn--primary nl-btn--sm droppedneedle-add-btn"
                            data-type="droppedneedle_wrapped" data-id="${id}"
                            data-name="Wrapped: ${escapeHtml(display)}"
                            data-user-key="${escapeHtml(userKey)}"
                            style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
                </div>
                <span class="snapin-row-label" title="${escapeHtml(display)}">${escapeHtml(display)}</span>
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
        <div class="snapin-row p-2 border rounded">
            <div class="snapin-row-actions">
                <button type="button"
                        class="nl-btn nl-btn--primary nl-btn--sm droppedneedle-server-add-btn"
                        data-type="droppedneedle_server_stats" data-id="droppedneedle-server-stats"
                        data-name="DroppedNeedle Server Stats"
                        style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
            </div>
            <span class="snapin-row-label" title="Server Stats (${droppedneedleServerPayload.year || ''})">Server Stats (${droppedneedleServerPayload.year || ''})</span>
        </div>`;
    host.appendChild(row);
};
buildDroppedNeedleServerRow();

function buildYearlyWrappedRow() {
    yearlyWrappedPayload = readJSONFromScript('yearly-wrapped-json');
    const host = document.getElementById('yearly-wrapped-list');
    if (!host) return;
    host.innerHTML = '';
    // The card is always present but hidden until data arrives, so a stats pull
    // reveals it without needing a page reload.
    const card = document.getElementById('yearly-wrapped-card');
    if (!yearlyWrappedPayload) {
        if (card) card.style.display = 'none';
        return;
    }
    if (card) card.style.display = '';

    const row = document.createElement('div');
    row.className = 'col-12 mb-2';
    row.innerHTML = `
        <div class="snapin-row p-2 border rounded">
            <div class="snapin-row-actions">
                <button type="button"
                        class="nl-btn nl-btn--primary nl-btn--sm yearly-wrapped-add-btn"
                        data-type="yearly_wrapped" data-id="yearly-wrapped"
                        data-name="Year in Plex"
                        style="font-size: .8rem; padding: .25rem .5rem;">Add</button>
            </div>
            <span class="snapin-row-label" title="Year in Plex">Year in Plex</span>
        </div>`;
    host.appendChild(row);
};
buildYearlyWrappedRow();
