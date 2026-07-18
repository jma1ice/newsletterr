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

    // user-info toggle: mirror the server-side skip of the Most Active Users stat
    if (title === "Most Active Users" && window.APP?.includeUserInfo === 'disabled') {
        return '';
    }

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
            cells.push(escapeHtml(row.section_name || ''));
        } else if (title === "Most Active Users") {
            cells.push(escapeHtml(row.user || ''));
        } else if (title === "Most Active Platforms") {
            cells.push(escapeHtml(row.platform || ''));
        } else {
            let titleCell = escapeHtml(row.title || '');
            if (showStatCoverArt && coverArtTypes.includes(title) && (row.thumb || row.grandparent_thumb)) {
                const thumbPath = row.thumb || row.grandparent_thumb;
                titleCell = `<img src="/proxy-art${escapeHtml(thumbPath)}" style="height:38px;width:auto;border-radius:3px;margin-right:7px;vertical-align:middle;">${titleCell}`;
            }
            cells.push(titleCell);
        }

        const skipYearStats = ["Most Active Libraries", "Library Item Counts", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"];
        if (!skipYearStats.includes(title)) {
            cells.push(escapeHtml(row.year || ''));
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
            cells.push(escapeHtml(row.content_rating || ''));
            cells.push(row.rating ? escapeHtml(`${row.rating}`) : 'NA');
        }

        if (title === "Most Concurrent Streams" || title === "Library Item Counts") {
            cells.push(row.count || 0);
        }

        return cells;
    }
    
    const headers = getStatHeaders(title);
    const headerHTML = headers.map(h => `<th>${h}</th>`).join('');
    
    const showUserAvatars = title === "Most Active Users" && window.APP?.includeUserInfo !== 'disabled';
    const rowsHTML = rows.map(row => {
        const cells = getStatCells(title, row);
        if (showUserAvatars && row.user_thumb) {
            cells[0] = `<img src="${escapeHtml(row.user_thumb)}" style="height:32px;width:32px;border-radius:50%;object-fit:cover;margin-right:7px;vertical-align:middle;" alt="">${cells[0]}`;
        }
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

    // user-info toggle: mirror the server-side skip of the top-users graphs
    if (window.APP?.includeUserInfo === 'disabled' &&
        (commandInfo?.name === 'Plays by Top Users' || commandInfo?.name === 'Stream Type by Top Users')) {
        return '';
    }

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
        return `<div class="recently-added"><p style="text-align: center; color: var(--email-muted); padding: 20px;">No recently added items found${libraryFilter ? ` for ${escapeHtml(libraryFilter)}` : ''}</p></div>`;
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
                    <img src="${escapeHtml(imgURL)}" style="width: 100%; height: 100%; object-fit: cover; display: block;" alt="${escapeHtml(item.title)}">
                </div>
                <div style="padding: 6px;">
                    <div style="font-weight: bold; font-size: 14px; color: var(--email-text); margin-bottom: 4px; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                        ${escapeHtml(item.title)}
                    </div>
                    <div style="font-size: 10px; color: var(--email-muted); margin-bottom: 8px; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                        ${escapeHtml([item.sub, item.duration, item.contentRating, item.added ? 'Added ' + item.added : ''].filter(Boolean).join(' • '))}
                    </div>
                    ${(item.summary && (window.APP?.raShowDescription !== 'disabled')) ? `
                        <div style="font-size: 11px; color: var(--email-text); opacity: 0.8; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden;">
                            ${escapeHtml(item.summary)}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;

        if (item.plex_url) {
            return `
                <a href="${escapeHtml(item.plex_url)}"
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
        const formatMDY = (d) => `${d.getMonth() + 1}/${d.getDate()}/${String(d.getFullYear()).slice(-2)}`;
        const sinceDate = new Date(Date.now() - raCount * 864e5);
        raTitle = (libraryFilter ? `Added to ${libraryFilter}` : 'Recently Added') + ` ${formatMDY(sinceDate)} - ${formatMDY(new Date())}`;
    } else {
        raTitle = `Recently Added${libraryFilter ? ` - ${libraryFilter}` : ''}`;
    }
    return `
        <div class="recently-added">
            <h2>${escapeHtml(raTitle)}</h2>
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
        return `<div class="recommendations-block"><p style="text-align: center; color: var(--email-muted); padding: 0;">No recommendations for ${escapeHtml(userEmail)}</p></div>`;
    }

    return `
        <div class="recommendations-block" style="padding: 0;" data-recs-user="${escapeHtml(userKey)}">
            <h2 style="text-align: center; margin-top: 0; margin-bottom: 10px;">Recommendations for ${escapeHtml(userEmail)}</h2>
            ${sectionsHTML}
        </div>
    `;
}

function buildWrappedRankedListHTML(title, items, labelFn) {
    if (!items || !items.length) return '';
    const rows = items.map((item, i) => `
        <li style="margin: 4px 0; color: var(--email-text);">
            <strong>#${i + 1}</strong> ${escapeHtml(labelFn(item))}
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
        <div class="droppedneedle-wrapped-block" style="padding: 0;" data-wrapped-user="${escapeHtml(userKey)}">
            <h2 style="text-align: center; margin-top: 0; margin-bottom: 10px; color: var(--email-text);">
                ${escapeHtml(userDisplay)}'s ${data.year} Wrapped
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
        ? `<p style="color: var(--email-text);"><strong>Top Artist:</strong> ${escapeHtml(data.top_artist_sitewide.name)} (${data.top_artist_sitewide.listen_count} plays)</p>` : '';
    const topAlbum = data.top_album_sitewide
        ? `<p style="color: var(--email-text);"><strong>Top Album:</strong> ${escapeHtml(data.top_album_sitewide.name)} - ${escapeHtml(data.top_album_sitewide.artist_name)} (${data.top_album_sitewide.listen_count} plays)</p>` : '';

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

// Kept in sync by hand with app/emails/builders/stats.py:build_yearly_wrapped_html_with_cids
function buildYearlyWrappedPreviewHTML() {
    const statsData = yearlyWrappedPayload;
    if (!statsData || !statsData.length) {
        return `<div><p style="text-align: center; color: var(--email-muted); padding: 20px;">No yearly wrapped data available</p></div>`;
    }

    const firstRow = (title) => {
        const stat = statsData.find(s => s.stat_title === title && s.rows && s.rows.length);
        return stat ? stat.rows[0] : null;
    };

    const topMovie = firstRow('Most Watched Movies');
    const topShow = firstRow('Most Watched TV Shows');
    const topArtist = firstRow('Most Played Artists');
    const topUser = firstRow('Most Active Users');

    let totalPlays = 0;
    statsData.forEach(stat => {
        if (['Most Watched Movies', 'Most Watched TV Shows', 'Most Played Artists'].includes(stat.stat_title)) {
            (stat.rows || []).forEach(row => { totalPlays += parseInt(row.total_plays || 0, 10); });
        }
    });

    // Mirrors _thumb_src in build_yearly_wrapped_html_with_cids: proxy the row's
    // thumb (or grandparent_thumb) through /proxy-art. The user row has no proxyable thumb.
    const thumbSrc = (row) => {
        const path = row.thumb || row.grandparent_thumb;
        if (!path) return null;
        return path.startsWith('/proxy-art') ? path : `/proxy-art${path}`;
    };

    const highlights = [];
    const includeUserInfo = window.APP?.includeUserInfo !== 'disabled';
    if (topMovie) highlights.push(['🎬 Top Movie', topMovie.title || '', thumbSrc(topMovie), false]);
    if (topShow) highlights.push(['📺 Top Show', topShow.title || '', thumbSrc(topShow), false]);
    if (topArtist) highlights.push(['🎵 Top Artist', topArtist.title || '', thumbSrc(topArtist), false]);
    if (topUser && includeUserInfo) {
        const userThumb = topUser.user_thumb || null;
        highlights.push(['👤 Most Active', topUser.user || '', userThumb, true]);
    }

    if (!highlights.length && !totalPlays) {
        return '';
    }

    const highlightCells = highlights.map(([label, value, thumb, isRound]) => `
        <td style="text-align: center; padding: 12px; vertical-align: top; width: ${100 / Math.max(highlights.length, 1)}%;">
            <div style="font-size: 12px; color: rgba(255,255,255,0.85); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">${label}</div>
            ${thumb ? `<img src="${escapeHtml(thumb)}" alt="${escapeHtml(value)}" style="height:60px;${isRound ? 'width:60px;border-radius:50%;object-fit:cover;' : 'width:auto;border-radius:4px;'}display:block;margin:0 auto 6px;">` : ''}<div style="font-size: 15px; font-weight: bold; color: white; line-height: 1.3;">${escapeHtml(value)}</div>
        </td>
    `).join('');

    const displayYear = new Date().getFullYear();

    return `
        <div style="margin: 20px 0; border-radius: 12px; overflow: hidden; background: linear-gradient(135deg, var(--email-primary) 0%, var(--email-accent) 100%); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);">
            <div style="padding: 20px 20px 4px 20px; text-align: center;">
                <div style="font-size: 13px; color: rgba(255,255,255,0.85); text-transform: uppercase; letter-spacing: 0.1em;">Year in Plex</div>
                <div style="font-size: 26px; font-weight: bold; color: white; margin: 4px 0 4px 0;">${displayYear} Wrapped</div>
                ${totalPlays ? `<div style="font-size: 14px; color: rgba(255,255,255,0.9); margin-bottom: 8px;">~${totalPlays} plays this year</div>` : ''}
            </div>
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>${highlightCells}</tr>
            </table>
        </div>`;
}

function _comingSoonRelativeDate(dateStr) {
    if (!dateStr) return '';
    const dt = new Date(dateStr);
    if (isNaN(dt.getTime())) return '';
    const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((startOfDay(dt) - startOfDay(new Date())) / 864e5);
    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'tomorrow';
    if (diffDays > 1) return `in ${diffDays} days`;
    if (diffDays === -1) return 'yesterday';
    return `${Math.abs(diffDays)} days ago`;
}

// Mirrors upcoming_release_date in app/emails/builders/coming_soon.py. NOTE:
// Python parses in UTC; this uses browser-local time, so a UTC-midnight release
// can differ by a day between this preview and the emailed version.
function _comingSoonUpcomingReleaseDate(movie) {
    const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const today = startOfDay(new Date());
    let earliest = null;
    for (const field of ['inCinemas', 'digitalRelease', 'physicalRelease']) {
        const raw = movie[field];
        if (!raw) continue;
        const dt = new Date(raw);
        if (isNaN(dt.getTime())) continue;
        const d = startOfDay(dt);
        if (d >= today && (earliest === null || d < earliest)) {
            earliest = d;
        }
    }
    return earliest;
}

// Mirrors _poster_url in coming_soon.py. Calendar images often carry only
// remoteUrl (an absolute CDN link) with no local url, so fall back to it.
function _comingSoonPosterUrl(images) {
    if (!Array.isArray(images)) return null;
    const poster = images.find(img => img.coverType === 'poster' && (img.url || img.remoteUrl));
    if (poster) return poster.url || poster.remoteUrl;
    const any = images.find(img => img.url || img.remoteUrl);
    return any ? (any.url || any.remoteUrl) : null;
}

// Mirrors _arr_poster_src in coming_soon.py. Absolute remoteUrls go through the
// generic /proxy-img route; local paths through the *arr art proxy.
function _comingSoonPosterSrc(posterPath, arrPrefix) {
    if (!posterPath) return '';
    if (posterPath.startsWith('http')) return `/proxy-img?u=${encodeURIComponent(posterPath)}`;
    return `${arrPrefix}${posterPath.startsWith('/') ? posterPath : '/' + posterPath}`;
}

function _comingSoonCardHTML(title, subtitle, metaText, posterSrc) {
    title = escapeHtml(title); subtitle = escapeHtml(subtitle); metaText = escapeHtml(metaText);
    const posterHTML = posterSrc
        ? `<div style="position: relative; aspect-ratio: 2/3; background: #f8f9fa;"><img src="${escapeHtml(posterSrc)}" style="width: 100%; height: 100%; object-fit: cover; display: block;" alt="${title}"></div>`
        : '';
    return `
        <div style="
            background: var(--email-card-bg);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--email-border);
            width: 100%;
            margin: 0 auto;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
        ">
            ${posterHTML}
            <div style="padding: 6px; color: var(--email-text); min-height: 60px;">
                <div style="font-weight: bold; font-size: 14px; color: var(--email-text); margin-bottom: 1px; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${title}</div>
                ${subtitle ? `<div style="font-size: 11px; color: var(--email-text); opacity: 0.85; margin-bottom: 2px;">${subtitle}</div>` : ''}
                <div style="font-size: 10px; color: var(--email-muted);">${metaText}</div>
            </div>
        </div>
    `;
}

function _comingSoonGridHTML(cardsHTML, title, gridColumns) {
    if (!cardsHTML.length) {
        return `<div><p style="text-align: center; color: var(--email-muted); padding: 20px;">No upcoming items found.</p></div>`;
    }
    return `
        <div>
            <h2 style="text-align: center; margin: 0 0 10px 0; color: var(--email-text);">${title}</h2>
            <div style="
                display: grid;
                grid-template-columns: repeat(${gridColumns}, minmax(0, 1fr));
                gap: 12px;
                margin: 15px auto 0 auto;
                padding: 0;
                width: 80%;
            ">
                ${cardsHTML.join('')}
            </div>
        </div>
    `;
}

// Mirrors group_sonarr_episodes in app/emails/builders/coming_soon.py. Collapses
// full-season drops (2+ episodes, same series/season, same local air day) into
// one group entry; seasonNumber null never groups.
function _groupSonarrEpisodes(episodes) {
    const airDay = (ep) => ep.airDate || (ep.airDateUtc || '').slice(0, 10);
    const groups = [];
    const indexByKey = new Map();
    episodes.forEach(ep => {
        const series = ep.series || {};
        const season = ep.seasonNumber;
        let key = null;
        if (season != null) {
            key = `${series.id || series.title || ep.title}|${season}|${airDay(ep)}`;
        }
        if (key !== null && indexByKey.has(key)) {
            groups[indexByKey.get(key)].episodes.push(ep);
            return;
        }
        const entry = {series, season, episodes: [ep], airDate: airDay(ep)};
        if (key !== null) indexByKey.set(key, groups.length);
        groups.push(entry);
    });
    return groups;
}

// Kept in sync by hand with app/emails/builders/coming_soon.py:build_sonarr_coming_soon_html_with_cids
function buildSonarrComingSoonPreviewHTML() {
    const episodes = sonarrComingSoonPayload;
    if (!episodes || !episodes.length) {
        return `<div><p style="text-align: center; color: var(--email-muted); padding: 20px;">No upcoming episodes found.</p></div>`;
    }

    const gridColumns = parseInt(APP.comingSoonGridColumns) || 5;

    const cardsHTML = _groupSonarrEpisodes(episodes).map(group => {
        const series = group.series || {};
        const eps = group.episodes;
        const firstEp = eps[0];
        const seriesTitle = series.title || firstEp.title || 'Unknown';
        const season = group.season;
        const year = series.year || firstEp.year || '';
        const yearPrefix = year ? String(year) : '';
        const relative = _comingSoonRelativeDate(firstEp.airDateUtc || firstEp.airDate);
        const metaText = relative ? `Airs ${relative}` : '';

        let subtitle;
        if (eps.length >= 2) {
            const seasonLabel = season != null ? `Season ${season}` : 'New episodes';
            subtitle = [yearPrefix, `${seasonLabel} (${eps.length} episodes)`].filter(Boolean).join(' • ');
        } else {
            const seLabel = (season != null && firstEp.episodeNumber != null)
                ? `S${String(season).padStart(2, '0')}E${String(firstEp.episodeNumber).padStart(2, '0')}`
                : '';
            const seText = [seLabel, firstEp.title || ''].filter(Boolean).join(' - ');
            subtitle = [yearPrefix, seText].filter(Boolean).join(' • ');
        }

        const posterPath = _comingSoonPosterUrl(series.images) || _comingSoonPosterUrl(firstEp.images);
        const posterSrc = _comingSoonPosterSrc(posterPath, '/proxy-sonarr-art');

        return _comingSoonCardHTML(seriesTitle, subtitle, metaText, posterSrc);
    });

    return _comingSoonGridHTML(cardsHTML, 'Coming Soon (TV)', gridColumns);
}

// Kept in sync by hand with app/emails/builders/coming_soon.py:build_radarr_coming_soon_html_with_cids
function buildRadarrComingSoonPreviewHTML() {
    const movies = radarrComingSoonPayload;
    if (!movies || !movies.length) {
        return `<div><p style="text-align: center; color: var(--email-muted); padding: 20px;">No upcoming movies found.</p></div>`;
    }

    const gridColumns = parseInt(APP.comingSoonGridColumns) || 5;

    // Drop already-downloaded (hasFile) or already-released movies to match
    // filter_radarr_upcoming in coming_soon.py.
    const upcoming = movies.filter(m => !m.hasFile && _comingSoonUpcomingReleaseDate(m));
    if (!upcoming.length) {
        return `<div><p style="text-align: center; color: var(--email-muted); padding: 20px;">No upcoming movies found.</p></div>`;
    }

    const cardsHTML = upcoming.map(movie => {
        const title = movie.title || 'Unknown';
        const subtitle = movie.year ? String(movie.year) : '';
        const releaseDate = _comingSoonUpcomingReleaseDate(movie);
        const relative = _comingSoonRelativeDate(releaseDate);
        const metaText = relative ? `Releases ${relative}` : '';

        const posterPath = _comingSoonPosterUrl(movie.images);
        const posterSrc = _comingSoonPosterSrc(posterPath, '/proxy-radarr-art');

        return _comingSoonCardHTML(title, subtitle, metaText, posterSrc);
    });

    return _comingSoonGridHTML(cardsHTML, 'Coming Soon (Movies)', gridColumns);
}

// Mirrors TMDB_POSTER_BASE/_poster_src in app/emails/builders/ombi_requests.py.
// Ombi's posterPath is a public TMDB CDN fragment, so it goes through the
// generic /proxy-img route rather than an Ombi-specific art proxy.
function _ombiPosterSrc(posterPath) {
    if (!posterPath) return '';
    const url = posterPath.startsWith('http') ? posterPath : `https://image.tmdb.org/t/p/w300${posterPath}`;
    return _comingSoonPosterSrc(url, '');
}

// Mirrors _normalize_movie_request/_normalize_tv_request/filter_ombi_pending in
// app/emails/builders/ombi_requests.py
function _filterOmbiPending(payload) {
    const data = payload || {};
    const entries = [];

    (data.movies || []).forEach(req => {
        if (req.available || req.denied) return;
        entries.push({
            title: req.title || 'Unknown',
            year: (req.releaseDate || '').slice(0, 4),
            poster: req.posterPath,
            approved: !!req.approved,
            requestedDate: req.requestedDate || null,
        });
    });

    (data.tv || []).forEach(req => {
        const children = req.childRequests || [];
        if (!children.length) return;
        // A show stays only while some season is still pending. No pending
        // seasons means every one is resolved (available/denied, in any mix),
        // matching the drop in _normalize_tv_request/filter_ombi_pending.
        const pendingChildren = children.filter(c => !c.available && !c.denied);
        if (!pendingChildren.length) return;
        const relevant = pendingChildren;
        const requestedDates = children.map(c => c.requestedDate).filter(Boolean);
        entries.push({
            title: req.title || 'Unknown',
            year: (req.releaseDate || '').slice(0, 4),
            poster: req.posterPath,
            approved: relevant.some(c => c.approved),
            requestedDate: requestedDates.length ? requestedDates.sort().slice(-1)[0] : null,
        });
    });

    entries.sort((a, b) => new Date(b.requestedDate || 0) - new Date(a.requestedDate || 0));
    return entries;
}

// Kept in sync by hand with app/emails/builders/ombi_requests.py:build_ombi_requests_html_with_cids
function buildOmbiRequestsPreviewHTML() {
    const entries = _filterOmbiPending(ombiRequestsPayload);
    if (!entries.length) {
        return `<div><p style="text-align: center; color: var(--email-muted); padding: 20px;">No pending or approved requests found.</p></div>`;
    }

    const gridColumns = parseInt(APP.comingSoonGridColumns) || 5;

    const cardsHTML = entries.map(entry => {
        const status = entry.approved ? 'Approved' : 'Pending Approval';
        const relative = _comingSoonRelativeDate(entry.requestedDate);
        const metaText = [status, relative ? `Requested ${relative}` : ''].filter(Boolean).join(' • ');
        const posterSrc = _ombiPosterSrc(entry.poster);
        return _comingSoonCardHTML(entry.title, entry.year, metaText, posterSrc);
    });

    return _comingSoonGridHTML(cardsHTML, 'Recent Requests', gridColumns);
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
                <a href="${escapeHtml(href)}" style="text-decoration: none; color: inherit; display: block;" target="_blank" title="${linkTitle}">
                    <div style="position: relative; aspect-ratio: 2/3; background: #f8f9fa;">
                        <img src="${escapeHtml(posterURL)}" style="width: 100%; height: 100%; object-fit: cover; display: block;" alt="${escapeHtml(titleText)}">
                    </div>
                    <div style="padding: 8px;">
                        <div style="font-weight: bold; font-size: 12px; color: var(--email-text); line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                            ${escapeHtml(titleText)}
                        </div>
                        ${metaLine ? `<div style="font-size: 10px; color: var(--email-muted); margin-top: 2px;">${escapeHtml(metaLine)}</div>` : ''}
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
                            ">${escapeHtml(overview)}</div>
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
    const collectionTitle = escapeHtml(collection.title || 'Unknown Collection');
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
    
    let cardHtml;
    if (posterURL) {
        cardHtml = `
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
        cardHtml = `
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

    if (collection.plex_url) {
        return `<a href="${escapeHtml(collection.plex_url)}" style="text-decoration: none; color: inherit; display: block;" target="_blank">${cardHtml}</a>`;
    }
    return cardHtml;
}

function buildIndividualItemCard(item, themeColors) {
    const itemTitle = escapeHtml(item.title || item.name || 'Unknown Title');
    const year = item.year ? ` (${item.year})` : '';
    const type = item.type || 'unknown';
    const typeIcon = getTypeIcon(type);
    
    let subtitle = '';
    if (item.artist && type !== 'show') {
        subtitle = escapeHtml(item.artist);
    } else if (type === 'show' && item.season_count) {
        subtitle = `${item.season_count} seasons`;
    } else if (item.album && type === 'track') {
        subtitle = escapeHtml(item.album);
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
    
    let cardHtml;
    if (posterURL) {
        cardHtml = `
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
        cardHtml = `
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

    if (item.plex_url) {
        return `<a href="${escapeHtml(item.plex_url)}" style="text-decoration: none; color: inherit; display: block;" target="_blank">${cardHtml}</a>`;
    }
    return cardHtml;
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

    const itemsPerRow = parseInt(window.APP?.collectionsGridColumns) || 5;
    const fullRowCellWidth = `${(100 / itemsPerRow).toFixed(4)}%`;
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
                    width: ${fullRowCellWidth};
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
            <h2 style="${titleStyle}">${escapeHtml(title)}</h2>
            <table cellpadding="0" cellspacing="0" border="0" style="${tableStyle}">
                ${itemsHTML}
            </table>
        </div>
    `;
}

function buildPreviewEmailHTML(contentHTML, serverName, subject, emailHeaderTitle, logoFilename, logoWidth, customLogoFilename, themedCSS, logoPosition, hostedEnabled = false, hostedBaseUrl = '') {
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
        logoHTML = `<img src="${logoSrc}" alt="${escapeHtml(serverName)}" class="email-logo" style="max-width: ${logoWidth}px; width: auto; height: auto; display: block; margin-left: ${_ml}; margin-right: ${_mr};">`;
    }

    const viewOnlineHTML = (hostedEnabled && hostedBaseUrl) ? `
                    <div style="text-align: center; padding: 8px 15px; background-color: var(--email-secondary); color: var(--email-muted); font-size: 12px;">
                        <a href="${hostedBaseUrl.replace(/\/$/, '')}/newsletter" style="color: var(--email-accent); text-decoration: none;">View latest newsletter</a>
                    </div>` : '';

    const unsubscribeHTML = (hostedEnabled && hostedBaseUrl) ? `
                        <div style="margin-top: 10px;">
                            <a href="#">Unsubscribe</a>
                        </div>` : '';

    return `<!DOCTYPE html>
        <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>${escapeHtml(subject)}</title>
                ${themedCSS}
            </head>
            <body>
                <div class="email-container">
                    <div class="email-header">
                        ${logoHTML}
                        <h1 class="email-title">${emailHeaderTitle}</h1>
                    </div>
                    ${viewOnlineHTML}

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
                        </div>${unsubscribeHTML}
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
