let selectedItems = [];
const hideGraphPlayCounts = APP.hideGraphPlayCounts;
const statType = APP.statType;
const recentlyAddedMode = APP.recentlyAddedMode;
const raGridColumns = parseInt(APP.raGridColumns) || 5;
const recsGridColumns = parseInt(APP.recsGridColumns) || 5;
const showStatCoverArt = APP.statCoverArt === "enabled";
const _defaultIntroText = APP.defaultIntroText || '';
const _defaultOutroText = APP.defaultOutroText || '';
const _serverNameForDefaults = APP.serverName;
const _resolvedIntroDefault = _defaultIntroText || `You are receiving this email because you are a member of ${_serverNameForDefaults}.`;
const _resolvedOutroDefault = _defaultOutroText || 'Thanks for using Plex and for reading this newsletterr email!';
let statsList = [];
try {
    statsList = APP.statsList;
} catch (e) {
    statsList = [];
    console.error("Error parsing stats:", e);
}

function buildStatPreviewHTML(statId) {
    const statIndex = parseInt(statId.split('-')[1]);
    
    if (!statsList || !Array.isArray(statsList) || statIndex >= statsList.length) {
        console.warn(`Stat index ${statIndex} not found in stats array`);
        return `<div class="stats-card"><div class="stats-content"><div class="stats-header">Statistics data not available</div></div></div>`;
    }
    
    const stat = statsList[statIndex];
    if (!stat || !stat.rows || !Array.isArray(stat.rows)) {
        console.warn(`Stat data invalid for index ${statIndex}`);
        return `<div class="stats-card"><div class="stats-content"><div class="stats-header">Statistics data not available</div></div></div>`;
    }
    
    const title = stat.stat_title || 'Statistics';
    const rows = stat.rows;
    
    let backgroundElements = '';
    if (rows.length > 0) {
        const artwork = rows[0].art || rows[0].grandparent_thumb;
        if (artwork) {
            const artworkUrl = `/proxy-art${artwork}`;
            backgroundElements = `
                <div class="stats-bg-blur" style="background-image: url('${artworkUrl}');"></div>
                <div class="stats-overlay"></div>
            `;
        }
    }

    function getStatHeaders(title) {
        if (title === "Most Watched Movies" || title === "Most Watched TV Shows") {
            return ["Title", "Year", "Plays", "Hours Played", "Cert.", "Score"];
        } else if (title === "Most Popular Movies" || title === "Most Popular TV Shows") {
            return ["Title", "Year", "Plays", "Users", "Cert.", "Score"];
        } else if (title === "Most Played Artists") {
            return ["Author", "Year", "Plays", "Hours Played"];
        } else if (title === "Most Popular Artists") {
            return ["Author", "Year", "Plays", "Users"];
        } else if (title === "Recently Watched") {
            return ["Title", "Year", "Cert.", "Score"];
        } else if (title === "Most Active Libraries") {
            return ["Library", "Plays", "Hours Played"];
        } else if (title === "Library Item Counts") {
            return ["Library", "Item Count"];
        } else if (title === "Most Active Users") {
            return ["Username", "Plays", "Hours Played"];
        } else if (title === "Most Active Platforms") {
            return ["Platform", "Plays", "Hours Played"];
        } else if (title === "Most Concurrent Streams") {
            return ["Category", "Count"];
        }
        return ["Title", "Value"];
    }
    
    function getStatCells(title, row) {
        const cells = [];
        const coverArtTypes = ["Most Watched Movies", "Most Watched TV Shows", "Most Popular Movies", "Most Popular TV Shows", "Most Played Artists", "Most Popular Artists", "Recently Watched"];

        if (title === "Most Active Libraries" || title === "Library Item Counts") {
            cells.push(row.section_name || '');
        } else if (title === "Most Active Users") {
            cells.push(row.user || '');
        } else if (title === "Most Active Platforms") {
            cells.push(row.platform || '');
        } else {
            let titleCell = row.title || '';
            if (showStatCoverArt && coverArtTypes.includes(title) && (row.thumb || row.grandparent_thumb)) {
                const thumbPath = row.thumb || row.grandparent_thumb;
                titleCell = `<img src="/proxy-art${thumbPath}" style="height:38px;width:auto;border-radius:3px;margin-right:7px;vertical-align:middle;">${titleCell}`;
            }
            cells.push(titleCell);
        }

        const skipYearStats = ["Most Active Libraries", "Library Item Counts", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"];
        if (!skipYearStats.includes(title)) {
            cells.push(row.year || '');
        }

        if (!title.includes("Recently") && !title.includes("Concurrent") && title !== "Library Item Counts") {
            cells.push(row.total_plays || 0);
        }

        const hoursStats = ["Most Watched Movies", "Most Watched TV Shows", "Most Played Artists", "Most Active Libraries", "Most Active Users", "Most Active Platforms"];
        const usersStats = ["Most Popular Movies", "Most Popular TV Shows", "Most Popular Artists"];

        if (hoursStats.includes(title)) {
            const hours = Math.ceil((row.total_duration || 0) / 3600);
            cells.push(hours);
        } else if (usersStats.includes(title)) {
            cells.push(row.users_watched || '');
        }

        const skipRatingStats = ["Most Active Libraries", "Library Item Counts", "Most Played Artists", "Most Popular Artists", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"];
        if (!skipRatingStats.includes(title)) {
            cells.push(row.content_rating || '');
            cells.push(row.rating ? `${row.rating}` : 'NA');
        }

        if (title === "Most Concurrent Streams" || title === "Library Item Counts") {
            cells.push(row.count || 0);
        }

        return cells;
    }
    
    const headers = getStatHeaders(title);
    const headerHTML = headers.map(h => `<th>${h}</th>`).join('');
    
    const rowsHTML = rows.map(row => {
        const cells = getStatCells(title, row);
        const cellsHTML = cells.map(cell => `<td>${cell}</td>`).join('');
        return `<tr>${cellsHTML}</tr>`;
    }).join('');
    
    const dateSuffix = title === "Library Item Counts" ? "" : ` - Last ${currentTimeRange} days`;

    return `
        <div class="stats-card">
            ${backgroundElements}
            <div class="stats-content">
                <div class="stats-header">${title}${dateSuffix}</div>
                <table class="stats-table">
                    <thead><tr>${headerHTML}</tr></thead>
                    <tbody>${rowsHTML}</tbody>
                </table>
            </div>
        </div>
    `;
}

function buildGraphPreviewHTML(graphId) {
    loadIBMPlexSans();

    const graphIndex = parseInt(graphId.split('-')[1]);
    
    if (graphIndex >= graphCommands.length || graphIndex >= graphDataList.length) {
        return `
            <div style="margin: 20px 0; padding: 30px; background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 8px; text-align: center;">
                <h3 style="color: #6c757d; margin-bottom: 10px;">Graph data not available</h3>
                <p style="color: #6c757d; margin: 0; font-size: 14px;">Index ${graphIndex} out of range</p>
            </div>
        `;
    }
    
    const commandInfo = graphCommands[graphIndex];
    const graphData = graphDataList[graphIndex];
    
    if (!graphData || (!graphData.categories && !graphData.series)) {
        return `
            <div style="margin: 20px 0; padding: 30px; background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 8px; text-align: center;">
                <h3 style="color: #6c757d; margin-bottom: 10px; font-family: 'IBM Plex Sans';">${commandInfo.name}</h3>
                <p style="color: #6c757d; margin: 0; font-size: 14px;">No chart data available</p>
                <p style="color: #6c757d; margin: 5px 0 0; font-size: 12px; font-style: italic;">Interactive charts available in dashboard</p>
            </div>
        `;
    }
    
    let chart = Highcharts.charts.find(c => c && c.renderTo.id === graphId);
    
    if (!chart) {
        const possibleIds = [
            graphId,
            `chart-${graphIndex}`,
            `graph-${graphIndex}`,
            `preview-${graphId}`,
            graphId.replace('graph-', 'chart-')
        ];
        
        for (const id of possibleIds) {
            chart = Highcharts.charts.find(c => c && c.renderTo.id === id);
            if (chart) break;
        }
    }
    
    if (!chart) {
        console.log('No existing chart found for', graphId, ', creating one...');
        
        const tempContainer = document.createElement('div');
        tempContainer.id = `temp-${graphId}-${Date.now()}`;
        tempContainer.style.cssText = 'position: fixed; left: -9999px; top: -9999px; width: 800px; height: 400px;';
        document.body.appendChild(tempContainer);
        
        try {
            chart = Highcharts.chart(tempContainer.id, {
                chart: { 
                    type: 'line',
                    style: {
                        fontFamily: 'IBM Plex Sans, Segoe UI, Helvetica, Arial, sans-serif'
                    }
                },
                title: { text: commandInfo.name + ' - Last ' + currentTimeRange + ' days' },
                exporting: { enabled: true },
                xAxis: { categories: graphData.categories },
                yAxis: { title: { text: hideGraphPlayCounts ? null : (statType === 'duration' ? 'Duration' : 'Plays') }, labels: { enabled: !hideGraphPlayCounts } },
                tooltip: hideGraphPlayCounts ? { enabled: false } : {},
                series: graphData.series
            });
            
            renderedCharts.add(graphId);
            const nowDark = document.documentElement.classList.contains('dark');
            applyChartTheme(nowDark);
            
            console.log('Auto-created chart for preview:', graphId);
        } catch (error) {
            console.error('Error creating chart for preview:', error);
            document.body.removeChild(tempContainer);
            return `
                <div style="margin: 20px 0; padding: 30px; background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 8px; text-align: center;">
                    <h3 style="color: #6c757d; margin-bottom: 10px;">${commandInfo.name}</h3>
                    <p style="color: #6c757d; margin: 0; font-size: 14px;">Error creating chart</p>
                    <p style="color: #6c757d; margin: 5px 0 0; font-size: 12px; font-style: italic;">Try clicking "View" first to render the chart</p>
                </div>
            `;
        }
    }
    
    if (chart) {
        try {
            const svg = chart.getSVG();
            
            const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
            const svgUrl = URL.createObjectURL(svgBlob);
            
            const tempElements = document.querySelectorAll(`[id^="temp-${graphId}"]`);
            tempElements.forEach(el => {
                if (el.parentNode) el.parentNode.removeChild(el);
            });
            
            return `
                <div style="width: 100%; border-radius: 4px; text-align: center;">
                    <img src="${svgUrl}" style="max-width: 100%; height: auto; border-radius: 4px;" alt="${commandInfo.name}" onload="URL.revokeObjectURL(this.src)">
                </div>
            `;
            
        } catch (error) {
            console.error('Error processing graph', graphId, error);
            
            const tempElements = document.querySelectorAll(`[id^="temp-${graphId}"]`);
            tempElements.forEach(el => {
                if (el.parentNode) el.parentNode.removeChild(el);
            });
        }
    }
    
    return `
        <div style="margin: 20px 0; padding: 30px; background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 8px; text-align: center;">
            <h3 style="color: #6c757d; margin-bottom: 10px;">${commandInfo.name}</h3>
            <p style="color: #6c757d; margin: 0; font-size: 14px;">Chart rendering failed</p>
            <p style="color: #6c757d; margin: 5px 0 0; font-size: 12px; font-style: italic;">Try clicking "View" in the dashboard to render the chart first</p>
        </div>
    `;
}

function buildRecentlyAddedPreviewHTML(libraryFilter) {
    if (!recentPayload || recentPayload.length === 0) {
        return `<div class="recently-added"><p style="text-align: center; color: var(--email-muted); padding: 20px;">No recently added items available</p></div>`;
    }
    
    let allItems = [];
    recentPayload.forEach(section => {
        if (section && section.recently_added) {
            allItems = allItems.concat(section.recently_added);
        }
    });
    
    if (libraryFilter) {
        allItems = allItems.filter(item => 
            item.library_name && item.library_name.toLowerCase() === libraryFilter.toLowerCase()
        );
    }

    const seenShows = new Set();
    const deduplicated = [];
    
    for (const item of allItems) {
        const itemType = (item.media_type || item.type || '').toLowerCase();
        
        if (itemType === 'episode' || itemType === 'season') {
            const showId = item.grandparent_rating_key || item.grandparent_title;
            
            if (showId && !seenShows.has(showId)) {
                seenShows.add(showId);
                const displayItem = { ...item };
                displayItem.original_title = item.title;
                displayItem.title = item.grandparent_title || item.title;
                deduplicated.push(displayItem);
            }
        } else {
            deduplicated.push(item);
        }
    }
    
    allItems = deduplicated;
    
    if (allItems.length === 0) {
        return `<div class="recently-added"><p style="text-align: center; color: var(--email-muted); padding: 20px;">No recently added items found${libraryFilter ? ` for ${libraryFilter}` : ''}</p></div>`;
    }
    
    const gridItems = allItems.map(item => {
        const item_type = (item.media_type || item.type || '').toLowerCase();
        const title = item.title || item.full_title || item.parent_title || item.grandparent_title || '(untitled)';
        const sub = item.year || item.grandparent_title || item.parent_title || '';
        const thumbPath = pickThumb(item);
        let duration = '';
        if (item_type === 'album') {
            duration = item.duration || item.grandparent_title || item.parent_title || 'Audio';
        } else {
            duration = msToHMS(item.duration);
        }
        const contentRating = item.content_rating || item.media_rating || '';
        const added = formatDate(item.updated_at || item.originally_available_at);
        const library = item.library_name || item.section_name || '';

        let summary = '';
        if (item_type === 'episode' || item_type === 'season') {
            summary = item.grandparent_tagline || item.grandparent_summary || item.parent_summary || item.tagline || item.summary || '';
        } else {
            summary = item.tagline || item.summary || '';
        }
        
        return {
            title,
            sub,
            summary: summary,
            duration,
            added,
            thumb: thumbPath,
            library,
            plex_url: item.plex_url || '',
            contentRating
        };
    });
    
    const itemsHTML = gridItems.map(item => {
        const imgURL = item.thumb ? `/proxy-art${item.thumb.startsWith('/') ? item.thumb : '/' + item.thumb}` : '/static/img/no-poster.png';
        
        const cardContent = `
            <div style="
                position: relative;
                background: var(--email-card-bg);
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
                border: 1px solid var(--email-border);
                width: 100%;
                max-width: 200px;
                margin: 0 auto;
                height: 310px;
                display: flex;
                flex-direction: column;
            ">
                <div style="position: relative; aspect-ratio: 2/3; background: #f8f9fa;">
                    <img src="${imgURL}" style="width: 100%; height: 100%; object-fit: cover; display: block;" alt="${item.title}">
                </div>
                <div style="padding: 6px;">
                    <div style="font-weight: bold; font-size: 14px; color: var(--email-text); margin-bottom: 4px; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                        ${item.title}
                    </div>
                    <div style="font-size: 10px; color: var(--email-muted); margin-bottom: 8px; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                        ${[item.sub, item.duration, item.contentRating, item.added ? 'Added ' + item.added : ''].filter(Boolean).join(' • ')}
                    </div>
                    ${item.summary ? `
                        <div style="font-size: 11px; color: var(--email-text); opacity: 0.8; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden;">
                            ${item.summary}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;

        if (item.plex_url) {
            return `
                <a href="${item.plex_url}" 
                class="plex-link"
                style="text-decoration: none; color: inherit; display: block;" 
                target="_blank"
                title="Open in Plex">
                    ${cardContent}
                </a>
            `;
        }
        
        return cardContent;
    }).join('');
    
    const raCount = parseInt(document.getElementById('items_to_pull')?.value || '10');
    let raTitle;
    if (recentlyAddedMode === 'days' && raCount) {
        const sinceDate = new Date(Date.now() - raCount * 864e5);
        const mm = sinceDate.getMonth() + 1, dd = sinceDate.getDate(), yy = String(sinceDate.getFullYear()).slice(-2);
        raTitle = (libraryFilter ? `Added to ${libraryFilter}` : 'Recently Added') + ` since ${mm}/${dd}/${yy}`;
    } else {
        raTitle = `Recently Added${libraryFilter ? ` - ${libraryFilter}` : ''}`;
    }
    return `
        <div class="recently-added">
            <h2>${raTitle}</h2>
            <div style="
                display: grid;
                grid-template-columns: repeat(${raGridColumns}, minmax(0, 1fr));
                gap: 12px;
                margin: 15px auto 0 auto;
                padding: 0;
                width: 80%;
            ">
                ${itemsHTML}
            </div>
        </div>
    `;
}

function buildRecommendationsPreviewHTML(userKey) {
    if (!recsPayload || !userKey || !recsPayload[userKey]) {
        return `<div class="recommendations-block"><p style="text-align: center; color: var(--email-muted); padding: 20px;">No recommendations available for this user</p></div>`;
    }
    
    const userRecs = recsPayload[userKey];
    const userEmail = getUserDisplayName(userKey);
    
    let sectionsHTML = '';
    
    if (userRecs.movie_posters && userRecs.movie_posters.length > 0) {
        sectionsHTML += buildRecommendationsSectionHTML(
            userRecs.movie_posters.slice(0, 20), 
            userRecs.movie_posters_unavailable?.slice(0, 20) || [], 
            'Recommended Movies'
        );
    }
    
    if (userRecs.show_posters && userRecs.show_posters.length > 0) {
        sectionsHTML += buildRecommendationsSectionHTML(
            userRecs.show_posters.slice(0, 20), 
            userRecs.show_posters_unavailable?.slice(0, 20) || [], 
            'Recommended TV Shows'
        );
    }
    
    if (!sectionsHTML) {
        return `<div class="recommendations-block"><p style="text-align: center; color: var(--email-muted); padding: 0;">No recommendations for ${userEmail}</p></div>`;
    }
    
    return `
        <div class="recommendations-block" style="padding: 0;" data-recs-user="${userKey}">
            <h2 style="text-align: center; margin-top: 0; margin-bottom: 10px;">Recommendations for ${userEmail}</h2>
            ${sectionsHTML}
        </div>
    `;
}

function buildWrappedRankedListHTML(title, items, labelFn) {
    if (!items || !items.length) return '';
    const rows = items.map((item, i) => `
        <li style="margin: 4px 0; color: var(--email-text);">
            <strong>#${i + 1}</strong> ${labelFn(item)}
            <span style="color: var(--email-muted); font-size: 0.85em;"> - ${item.listen_count} plays</span>
        </li>`).join('');
    return `
        <div style="margin-bottom: 16px;">
            <h3 style="margin-bottom: 6px; color: var(--email-text);">${title}</h3>
            <ol style="padding-left: 20px; margin: 0;">${rows}</ol>
        </div>`;
}

function buildDroppedNeedleWrappedPreviewHTML(userKey) {
    const data = droppedneedleWrappedPayload && userKey ? droppedneedleWrappedPayload[userKey] : null;
    if (!data || !data.has_data) {
        return `<div class="droppedneedle-wrapped-block"><p style="text-align: center; color: var(--email-muted); padding: 20px;">No DroppedNeedle wrapped stats available for this user</p></div>`;
    }

    const userDisplay = getUserDisplayName(userKey);
    const sections = [
        buildWrappedRankedListHTML('Top Artists', data.top_artists, a => a.name),
        buildWrappedRankedListHTML('Top Tracks', data.top_tracks, t => `${t.name} - ${t.artist_name}`),
        buildWrappedRankedListHTML('Top Albums', data.top_albums, al => `${al.name} - ${al.artist_name}`),
        buildWrappedRankedListHTML('Top Genres', data.top_genres, g => g.genre),
    ].join('');

    return `
        <div class="droppedneedle-wrapped-block" style="padding: 0;" data-wrapped-user="${userKey}">
            <h2 style="text-align: center; margin-top: 0; margin-bottom: 10px; color: var(--email-text);">
                ${userDisplay}'s ${data.year} Wrapped
            </h2>
            <p style="text-align: center; color: var(--email-muted); margin-bottom: 16px;">
                ~${data.total_listens_estimated} plays tracked &bull; ${data.loved_tracks_count} loved tracks
            </p>
            ${sections}
        </div>`;
}

function buildDroppedNeedleServerStatsPreviewHTML() {
    const data = droppedneedleServerPayload;
    if (!data) {
        return `<div class="droppedneedle-server-block"><p style="text-align: center; color: var(--email-muted); padding: 20px;">No DroppedNeedle server stats available</p></div>`;
    }

    const leaderboardHTML = buildWrappedRankedListHTML(
        'Top Listeners', data.leaderboard, entry => entry.display_name
    );
    const topArtist = data.top_artist_sitewide
        ? `<p style="color: var(--email-text);"><strong>Top Artist:</strong> ${data.top_artist_sitewide.name} (${data.top_artist_sitewide.listen_count} plays)</p>` : '';
    const topAlbum = data.top_album_sitewide
        ? `<p style="color: var(--email-text);"><strong>Top Album:</strong> ${data.top_album_sitewide.name} - ${data.top_album_sitewide.artist_name} (${data.top_album_sitewide.listen_count} plays)</p>` : '';

    return `
        <div class="droppedneedle-server-block" style="padding: 0;">
            <h2 style="text-align: center; margin-top: 0; margin-bottom: 10px; color: var(--email-text);">
                Server Stats - ${data.year}
            </h2>
            <p style="text-align: center; color: var(--email-muted); margin-bottom: 16px;">
                ~${data.total_listens_estimated} plays across ${data.total_users_tracked} listeners
            </p>
            ${topArtist}
            ${topAlbum}
            ${leaderboardHTML}
        </div>`;
}

function buildRecommendationsSectionHTML(availableItems, unavailableItems, title) {
    const allItems = [...availableItems, ...unavailableItems];
    
    const itemsHTML = allItems.map((item, index) => {
        const isUnavailable = index >= availableItems.length;
        const posterURL = item.url ? `/proxy-img?u=${encodeURIComponent(item.url)}` : '/static/img/no-poster.png';
        const titleText = item.title || 'Unknown';
        const year = item.year || '';
        const vote = item.vote ? `★ ${item.vote.toFixed(1)}` : '';
        const overview = item.overview || '';
        const runtime = item.runtime || '';

        let href;
        let linkTitle;
        if (isUnavailable) {
            href = item.href || '#';
            linkTitle = 'Request on Overseerr';
        } else {
            if (item.plex_url) {
                href = item.plex_url;
                linkTitle = 'Open in Plex';
            } else if (item.rating_key && item.machine_id) {
                const metadataKey = encodeURIComponent(`/library/metadata/${item.rating_key}`);
                href = `plex://preplay?metadataKey=${metadataKey}&server=${item.machine_id}`;
                linkTitle = 'Open in Plex';
            } else {
                const searchQuery = encodeURIComponent(titleText);
                href = `https://app.plex.tv/desktop#!/search?query=${searchQuery}`;
                linkTitle = 'Search in Plex';
            }
        }
        
        const unavailableStyle = isUnavailable ? 'opacity: 0.7; filter: grayscale(30%);' : '';
        const metaLine = [year, vote, runtime, isUnavailable ? 'Unavailable' : ''].filter(Boolean).join(' • ');

        return `
            <div style="
                position: relative;
                background: var(--email-card-bg);
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border: 1px solid var(--email-border);
                ${unavailableStyle}
                width: 100%;
                max-width: 200px;
                margin: 0 auto;
            ">
                <a href="${href}" style="text-decoration: none; color: inherit; display: block;" target="_blank" title="${linkTitle}">
                    <div style="position: relative; aspect-ratio: 2/3; background: #f8f9fa;">
                        <img src="${posterURL}" style="width: 100%; height: 100%; object-fit: cover; display: block;" alt="${titleText}">
                    </div>
                    <div style="padding: 8px;">
                        <div style="font-weight: bold; font-size: 12px; color: var(--email-text); line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                            ${titleText}
                        </div>
                        ${metaLine ? `<div style="font-size: 10px; color: var(--email-muted); margin-top: 2px;">${metaLine}</div>` : ''}
                        ${overview ? `
                            <div style="
                                font-size: 10px;
                                color: var(--email-text);
                                opacity: 0.8;
                                line-height: 1.3;
                                margin-top: 4px;
                                padding-top: 4px;
                                border-top: 1px solid var(--email-border);
                                display: -webkit-box;
                                -webkit-line-clamp: 3;
                                -webkit-box-orient: vertical;
                                overflow: hidden;
                            ">${overview}</div>
                        ` : ''}
                    </div>
                </a>
            </div>
        `;
    }).join('');
    
    return `
        <div style="margin: 20px 5px;">
            <h3 style="color: var(--email-text); margin-bottom: 5px; padding-bottom: 0;">${title}</h3>
            <div style="
                display: grid;
                grid-template-columns: repeat(${recsGridColumns}, minmax(0, 1fr));
                gap: 12px;
                padding: 0;
                margin: 0 auto 0 auto;
                width: 80%;
            ">
                ${itemsHTML}
            </div>
        </div>
    `;
}

function getItemPosterURL(item) {
    const candidates = [item.thumb, item.art, item.parent_thumb, item.grandparent_thumb];
    for (const candidate of candidates) {
        if (candidate) {
            return `/proxy-art${candidate.startsWith('/') ? candidate : '/' + candidate}`;
        }
    }
    return '/static/img/no-poster.png';
}

function buildCollectionCard(collection, themeColors) {
    const collectionTitle = collection.title || 'Unknown Collection';
    const count = collection.childCount || 0;
    const subtype = collection.subtype || 'unknown';
    const typeIcon = subtype === 'movie' ? '📽️' : subtype === 'show' ? '📺' : '🎧';
    
    let posterURL = null;
    const thumbUrl = collection.thumb;
    const artUrl = collection.art;
    
    if (thumbUrl) {
        if (thumbUrl.startsWith('http')) {
            try {
                const url = new URL(thumbUrl);
                posterURL = `/proxy-art${url.pathname}`;
            } catch (e) {
                console.log('Failed to parse thumb URL:', thumbUrl);
            }
        } else {
            posterURL = `/proxy-art${thumbUrl.startsWith('/') ? thumbUrl : '/' + thumbUrl}`;
        }
    } else if (artUrl) {
        if (artUrl.startsWith('http')) {
            try {
                const url = new URL(artUrl);
                posterURL = `/proxy-art${url.pathname}`;
            } catch (e) {
                console.log('Failed to parse art URL:', artUrl);
            }
        } else {
            posterURL = `/proxy-art${artUrl.startsWith('/') ? artUrl : '/' + artUrl}`;
        }
    }
    
    if (posterURL) {
        return `
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: ${themeColors.card_bg};
                border-radius: 12px;
                width: 120px;
                margin: 0 auto;
            ">
                <tr>
                    <td style="padding: 0; line-height: 0; font-size: 0;">
                        <img src="${posterURL}" alt="${collectionTitle}" width="120" height="180" style="
                            display: block;
                            width: 120px;
                            height: 180px;
                            object-fit: cover;
                            border-radius: 12px 12px 0 0;
                            background-color: #f8f9fa;
                        ">
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px;">
                        <div style="
                            font-weight: bold;
                            font-size: 12px;
                            color: ${themeColors.text};
                            line-height: 1.2;
                            font-family: 'IBM Plex Sans';
                        ">${collectionTitle}</div>
                        <div style="
                            font-size: 10px;
                            color: ${themeColors.muted_text};
                            line-height: 1.2;
                            font-family: 'IBM Plex Sans';
                            margin-top: 2px;
                        ">${typeIcon} ${count} items</div>
                    </td>
                </tr>
            </table>
        `;
    } else {
        return `
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: ${themeColors.card_bg};
                border-radius: 12px;
                border: 1px solid ${themeColors.border};
                width: 120px;
                height: 180px;
                margin: 0 auto;
            ">
                <tr>
                    <td style="
                        text-align: center;
                        vertical-align: middle;
                        padding: 12px;
                    ">
                        <div style="
                            font-weight: bold;
                            font-size: 14px;
                            color: ${themeColors.text};
                            margin-bottom: 8px;
                            font-family: 'IBM Plex Sans';
                            padding: 2px;
                        ">${collectionTitle}</div>
                        <div style="
                            font-size: 11px;
                            color: ${themeColors.muted_text};
                            font-family: 'IBM Plex Sans';
                        ">${typeIcon} ${count} items</div>
                    </td>
                </tr>
            </table>
        `;
    }
}

function buildIndividualItemCard(item, themeColors) {
    const itemTitle = item.title || item.name || 'Unknown Title';
    const year = item.year ? ` (${item.year})` : '';
    const type = item.type || 'unknown';
    const typeIcon = getTypeIcon(type);
    
    let subtitle = '';
    if (item.artist && type !== 'show') {
        subtitle = item.artist;
    } else if (type === 'show' && item.season_count) {
        subtitle = `${item.season_count} seasons`;
    } else if (item.album && type === 'track') {
        subtitle = item.album;
    }
    
    let posterURL = null;
    const thumbUrl = item.thumb;
    
    if (thumbUrl) {
        if (thumbUrl.startsWith('http')) {
            try {
                const url = new URL(thumbUrl);
                posterURL = `/proxy-art${url.pathname}`;
            } catch (e) {
                console.log('Failed to parse thumb URL:', thumbUrl);
            }
        } else {
            posterURL = `/proxy-art${thumbUrl.startsWith('/') ? thumbUrl : '/' + thumbUrl}`;
        }
    }
    
    if (posterURL) {
        return `
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: ${themeColors.card_bg};
                border-radius: 12px;
                width: 120px;
                margin: 0 auto;
            ">
                <tr>
                    <td style="padding: 0; line-height: 0; font-size: 0;">
                        <img src="${posterURL}" alt="${itemTitle}${year}" width="120" height="180" style="
                            display: block;
                            width: 120px;
                            height: 180px;
                            object-fit: cover;
                            border-radius: 12px 12px 0 0;
                            background-color: #f8f9fa;
                        ">
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px;">
                        <div style="
                            font-weight: bold;
                            font-size: 11px;
                            color: ${themeColors.text};
                            line-height: 1.2;
                            font-family: 'IBM Plex Sans';
                        ">${itemTitle}${year}</div>
                        <div style="
                            font-size: 9px;
                            color: ${themeColors.muted_text};
                            line-height: 1.2;
                            font-family: 'IBM Plex Sans';
                            margin-top: 2px;
                        ">${subtitle ? typeIcon + ' ' + subtitle : typeIcon}</div>
                    </td>
                </tr>
            </table>
        `;
    } else {
        return `
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: ${themeColors.card_bg};
                border-radius: 12px;
                border: 1px solid ${themeColors.border};
                width: 120px;
                height: 180px;
                margin: 0 auto;
            ">
                <tr>
                    <td style="
                        text-align: center;
                        vertical-align: middle;
                        padding: 12px;
                        color: ${themeColors.text};
                        font-family: 'IBM Plex Sans';
                    ">
                        <div style="
                            font-size: 24px;
                            margin-bottom: 8px;
                        ">${typeIcon}</div>
                        <div style="
                            font-weight: bold;
                            font-size: 11px;
                            line-height: 1.2;
                            margin-bottom: 4px;
                        ">${itemTitle}${year}</div>
                        ${subtitle ? `
                            <div style="
                                font-size: 9px;
                                color: ${themeColors.muted_text};
                                line-height: 1.2;
                            ">${subtitle}</div>
                        ` : ''}
                    </td>
                </tr>
            </table>
        `;
    }
}

function getTypeIcon(type) {
    switch (type) {
        case 'movie': return '🎬';
        case 'show': return '📺';
        case 'album': return '💿';
        case 'track': return '🎵';
        case 'artist': return '🎤';
        default: return '📄';
    }
}

function getCollectionGroupIndex(collection) {
    for (let i = 0; i < selectedItems.length; i++) {
        if (selectedItems[i].type === 'collection_group' && selectedItems[i].collections) {
            for (let j = 0; j < selectedItems[i].collections.length; j++) {
                if (selectedItems[i].collections[j].key === collection.key) {
                    return i;
                }
            }
        }
    }
    return 0;
}

function buildCollectionPreviewHTMLForEmail(title, collections, stableGroupId = 'group-0') {
    const themeColors = {
        card_bg: 'var(--email-card-bg)',
        text: 'var(--email-text)', 
        border: 'var(--email-border)',
        muted_text: 'var(--email-muted)'
    };
    
    if (!collections || collections.length === 0) {
        return `
            <div style="background-color: ${themeColors.card_bg}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid ${themeColors.border}; font-family: 'IBM Plex Sans';">
                <p style="text-align: center; color: ${themeColors.muted_text}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans';">No collections available.</p>
            </div>
        `;
    }

    let allItemsToDisplay = [];
    let hasExpandedCollections = false;
    
    collections.forEach((collection, index) => {
        const collectionId = `${stableGroupId}-${index}-${collection.key}`;
        const expandedItems = window.expandedCollections[collectionId];
        
        if (expandedItems && Object.keys(expandedItems).length > 0) {
            hasExpandedCollections = true;
            Object.values(expandedItems).forEach(item => {
                allItemsToDisplay.push({
                    ...item,
                    isIndividualItem: true,
                    originalCollection: collection.title
                });
            });
        } else {
            allItemsToDisplay.push({
                ...collection,
                isIndividualItem: false
            });
        }
    });

    const itemsPerRow = 5;
    let itemsHTML = "";
    
    for (let i = 0; i < allItemsToDisplay.length; i += itemsPerRow) {
        const rowItems = allItemsToDisplay.slice(i, i + itemsPerRow);
        const isPartialRow = rowItems.length < itemsPerRow;
        
        if (isPartialRow) {
            const itemsCount = rowItems.length;
            
            let rowHTML = `<tr><td colspan="${itemsPerRow}" style="text-align: center; padding: 8px;">`;
            rowHTML += '<table cellpadding="0" cellspacing="0" border="0" style="margin: 0 auto; border-collapse: separate;">';
            rowHTML += '<tr>';
            
            rowItems.forEach((item, j) => {
                let cellSpacing = "0";
                if (itemsCount === 2) {
                    cellSpacing = j === 0 ? "60px" : "0";
                } else if (itemsCount === 3) {
                    cellSpacing = j < 2 ? "40px" : "0";
                } else if (itemsCount === 4) {
                    cellSpacing = j < 3 ? "20px" : "0";
                } else if (itemsCount > 1) {
                    cellSpacing = j < itemsCount - 1 ? "6px" : "0";
                }
                
                const cardHTML = item.isIndividualItem 
                    ? buildIndividualItemCard(item, themeColors)
                    : buildCollectionCard(item, themeColors);
                rowHTML += `<td style="vertical-align: top; padding-right: ${cellSpacing};">${cardHTML}</td>`;
            });
            
            rowHTML += '</tr></table></td></tr>';
            itemsHTML += rowHTML;
        } else {
            let rowHTML = "<tr style='text-align: center;'>";
            
            rowItems.forEach((item) => {
                const cellStyle = `
                    width: 20%;
                    padding: 6px;
                    vertical-align: top;
                    font-family: 'IBM Plex Sans';
                `;
                
                const cardHTML = item.isIndividualItem 
                    ? buildIndividualItemCard(item, themeColors)
                    : buildCollectionCard(item, themeColors);
                rowHTML += `<td style="${cellStyle}">${cardHTML}</td>`;
            });
            
            rowHTML += "</tr>";
            itemsHTML += rowHTML;
        }
    }
    
    const containerStyle = `
        background-color: ${themeColors.card_bg};
        border-radius: 8px;
        margin: 20px 0;
        border: 1px solid ${themeColors.border};
        font-family: 'IBM Plex Sans';
    `;
    
    const titleStyle = `
        text-align: center;
        color: ${themeColors.text};
        margin: 0 0 20px 0;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans';
    `;
    
    const tableStyle = `
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        padding: 0;
    `;
    
    return `
        <div style="${containerStyle}">
            <h2 style="${titleStyle}">${title}</h2>
            <table cellpadding="0" cellspacing="0" border="0" style="${tableStyle}">
                ${itemsHTML}
            </table>
        </div>
    `;
}

function buildPreviewEmailHTML(contentHTML, serverName, subject, emailHeaderTitle, logoFilename, logoWidth, customLogoFilename, themedCSS, logoPosition) {
    let logoHTML = "";
    let logoSrc = "";
    if (logoFilename && logoWidth) {
        if (logoFilename == 'custom') {
            logoSrc = `/static/uploads/logos/${customLogoFilename}`;
        } else {
            logoSrc = `/static/img/${logoFilename}`;
        }
        const _ml = logoPosition === 'left' ? '0' : 'auto';
        const _mr = logoPosition === 'right' ? '0' : 'auto';
        logoHTML = `<img src="${logoSrc}" alt="${serverName}" class="email-logo" style="max-width: ${logoWidth}px; width: auto; height: auto; display: block; margin-left: ${_ml}; margin-right: ${_mr};">`;
    }

    return `<!DOCTYPE html>
        <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>${subject}</title>
                ${themedCSS}
            </head>
            <body>
                <div class="email-container">
                    <div class="email-header">
                        ${logoHTML}
                        <h1 class="email-title">${emailHeaderTitle}</h1>
                    </div>
                    
                    <div class="email-content">
                        ${contentHTML}
                    </div>
                    
                    <div class="email-footer">
                        <div style="margin-bottom: 10px;">
                            Generated for Plex Media Server by 
                            <a href="https://github.com/jma1ice/newsletterr">newsletterr</a>
                        </div>
                        <div>
                            newsletterr is not affiliated with or a product of Plex, Inc.
                        </div>
                    </div>
                </div>
            </body>
        </html>`;
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, testing preview...');
    const frame = document.getElementById('preview');
    if (frame) {
        frame.srcdoc = '<html><body><h1>Test Preview</h1><p>If you can see this, the iframe is working.</p></body></html>';
        console.log('Test preview set');
    } else {
        console.error('Preview iframe not found on DOM load!');
    }
    
    setTimeout(() => {
        console.log('Running initial updatePreview...');
        updatePreview();
    }, 100);
});

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('email_header_title').addEventListener('input', debouncedUpdatePreview);
});
