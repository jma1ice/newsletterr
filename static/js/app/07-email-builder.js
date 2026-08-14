window.expandedCollections = {};
window.collapsedCollectionsUI = {};

// Chevron for the collection expand/collapse toggle: points down when the
// collection is expanded, right when collapsed (matches the cache/BCC cards).
function collectionToggleIcon(expanded) {
    const points = expanded ? '6 9 12 15 18 9' : '9 6 15 12 9 18';
    return `<svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polyline points="${points}"/></svg>`;
}

function richTextToolbar(blockId) {
    const icon = (paths) =>
        `<svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths}</svg>`;
    const btn = (cmd, label, inner) =>
        `<button type="button" class="rte-btn" data-cmd="${cmd}" data-textblock-id="${blockId}"
            title="${label}" aria-label="${label}" aria-pressed="false">${inner}</button>`;

    return `
        <div class="rte-toolbar" role="toolbar" aria-label="Text formatting">
            ${btn('bold', 'Bold', '<strong>B</strong>')}
            ${btn('italic', 'Italic', '<em>I</em>')}
            ${btn('underline', 'Underline', '<span style="text-decoration: underline;">U</span>')}
            <span class="rte-sep" aria-hidden="true"></span>
            ${btn('justifyLeft', 'Align left', icon('<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="18" y2="18"/>'))}
            ${btn('justifyCenter', 'Align center', icon('<line x1="3" y1="6" x2="21" y2="6"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="5" y1="18" x2="19" y2="18"/>'))}
            ${btn('justifyRight', 'Align right', icon('<line x1="3" y1="6" x2="21" y2="6"/><line x1="9" y1="12" x2="21" y2="12"/><line x1="6" y1="18" x2="21" y2="18"/>'))}
            <span class="rte-sep" aria-hidden="true"></span>
            ${btn('insertUnorderedList', 'Bulleted list', icon('<line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="4.5" cy="6" r="1.2"/><circle cx="4.5" cy="12" r="1.2"/><circle cx="4.5" cy="18" r="1.2"/>'))}
            ${btn('insertOrderedList', 'Numbered list', icon('<line x1="10" y1="6" x2="20" y2="6"/><line x1="10" y1="12" x2="20" y2="12"/><line x1="10" y1="18" x2="20" y2="18"/><path d="M4 4.5h1V8"/><path d="M3.6 11.4h1.8L3.6 14.6h1.9"/><path d="M3.7 17h1.6v1.4H3.9v1.2h1.4"/>'))}
            <span class="rte-sep" aria-hidden="true"></span>
            ${btn('createLink', 'Insert link', icon('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'))}
            ${btn('linkUnderline', 'Underline on the selected link', icon('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/><line x1="4" y1="21" x2="20" y2="21"/>'))}
            <label class="rte-color-wrap" title="Text color">
                <span class="rte-color-glyph" aria-hidden="true">A</span>
                <input type="color" class="rte-color" data-textblock-id="${blockId}"
                    value="#000000" aria-label="Text color">
            </label>
            ${btn('removeFormat', 'Clear formatting', icon('<path d="M4 7V4h16v3"/><path d="M5 20h6"/><path d="M13 4 8 20"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="21" y1="15" x2="15" y2="21"/>'))}
        </div>
    `;
}

function textBlockStyleControls(index, item) {
    const size = item.fontSize || '';
    const family = item.fontFamily || '';
    return `
        <div class="d-flex gap-2 align-items-center flex-wrap mt-1 text-block-style-row">
            <label style="font-size: 0.8rem; white-space: nowrap;">Font:</label>
            <select class="form-select form-select-sm text-block-font" data-index="${index}" style="width: auto;">
                <option value=""          ${family === ''          ? 'selected' : ''}>Default</option>
                <option value="sans"      ${family === 'sans'      ? 'selected' : ''}>Sans</option>
                <option value="serif"     ${family === 'serif'     ? 'selected' : ''}>Serif</option>
                <option value="mono"      ${family === 'mono'      ? 'selected' : ''}>Monospace</option>
                <option value="condensed" ${family === 'condensed' ? 'selected' : ''}>Condensed</option>
            </select>
            <label style="font-size: 0.8rem; white-space: nowrap;">Size:</label>
            <input type="number" class="form-control form-control-sm text-block-size"
                data-index="${index}" min="8" max="96" placeholder="auto"
                title="Font size in px for the whole block. Blank uses the block's built-in size."
                value="${escapeHtml(String(size))}" style="width: 5em;">
        </div>
    `;
}

const HEADING_ITEM_TYPES = new Set([
    'stat',
    'recently added',
    'recently_released',
    'most_watched',
    'recommendations',
    'sonarr_coming_soon',
    'radarr_coming_soon',
    'ombi_requests',
    'seerr_requests',
    'top_viewer',
    'random_pick',
    'featured_pick',
    'yearly_wrapped',
    'droppedneedle_wrapped',
    'droppedneedle_server_stats',
]);

function itemHeadingControls(index, item) {
    if (!HEADING_ITEM_TYPES.has(item.type)) return '';
    const hidden = !!item.hideHeading;
    return `
        <div class="d-flex gap-2 align-items-center flex-wrap mt-2 snapin-heading-row">
            <label style="font-size: 0.8rem; white-space: nowrap;">Heading:</label>
            <input type="text" class="form-control form-control-sm snapin-heading-input"
                data-index="${index}" placeholder="Section default"
                title="Blank uses this snap-in's built-in heading"
                value="${escapeHtml(item.heading || '')}"
                ${hidden ? 'disabled' : ''} style="flex: 1 1 10em; min-width: 0;">
            <div class="form-check mb-0">
                <input class="form-check-input snapin-heading-hide" type="checkbox"
                    id="hide-heading-${index}" data-index="${index}" ${hidden ? 'checked' : ''}>
                <label class="form-check-label" for="hide-heading-${index}"
                    style="font-size: 0.8rem; white-space: nowrap;">Hide</label>
            </div>
        </div>
    `;
}

function collectionPeekIcon(hidden) {
    const inner = hidden
        ? '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>'
        : '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
    return `<svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${inner}</svg>`;
}

function itemMoveControls(index, total) {
    const chevrons = (up) => {
        const points = up ? '17 11 12 6 7 11|17 18 12 13 7 18' : '7 13 12 18 17 13|7 6 12 11 17 6';
        const [a, b] = points.split('|');
        return `<svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polyline points="${a}"/><polyline points="${b}"/></svg>`;
    };
    return `
        <button type="button" class="nl-btn nl-btn--ghost nl-btn--sm nl-btn--icon item-move-btn"
            data-index="${index}" data-edge="top" ${index === 0 ? 'disabled' : ''}
            title="Move to top" aria-label="Move to top">${chevrons(true)}</button>
        <button type="button" class="nl-btn nl-btn--ghost nl-btn--sm nl-btn--icon item-move-btn"
            data-index="${index}" data-edge="bottom" ${index === total - 1 ? 'disabled' : ''}
            title="Move to bottom" aria-label="Move to bottom">${chevrons(false)}</button>
    `;
}

const COLLECTION_KEY_SEP = '::';

function collectionExpansionKey(stableGroupId, collectionKey) {
    return `${stableGroupId}${COLLECTION_KEY_SEP}${collectionKey}`;
}

function stableGroupIdFor(item, groupArrayIndex) {
    return item.id || `group-${groupArrayIndex}`;
}

function eachGroupCollection(fn) {
    selectedItems.forEach((item, groupArrayIndex) => {
        if (!item || item.type !== 'collection_group') return;
        const stableGroupId = stableGroupIdFor(item, groupArrayIndex);
        (item.collections || []).forEach((col, collectionIndex) => {
            fn({ stableGroupId, groupArrayIndex, col, collectionIndex });
        });
    });
}

function convertExpandedCollectionsForBackend() {
    const converted = {};
    eachGroupCollection(({ stableGroupId, groupArrayIndex, col, collectionIndex }) => {
        const items = window.expandedCollections[collectionExpansionKey(stableGroupId, col.key)];
        if (items) converted[`${groupArrayIndex}-${collectionIndex}-${col.key}`] = items;
    });
    return converted;
}

function convertExpandedCollectionsFromBackend(stored) {
    const restored = {};
    if (!stored) return restored;
    eachGroupCollection(({ stableGroupId, groupArrayIndex, col, collectionIndex }) => {
        const items =
            stored[`${groupArrayIndex}-${collectionIndex}-${col.key}`] ||
            // templates saved while the UI key was the stored one
            stored[`${stableGroupId}-${collectionIndex}-${col.key}`] ||
            stored[collectionExpansionKey(stableGroupId, col.key)];
        if (items) restored[collectionExpansionKey(stableGroupId, col.key)] = items;
    });
    return restored;
}

function findGroupIndexByStableId(stableId) {
    for (let i = 0; i < selectedItems.length; i++) {
        if (selectedItems[i].id === stableId || `group-${i}` === stableId) {
            return i;
        }
    }
    return -1;
}

function buildCollectionItemsDisplay(items) {
    if (!items || Object.keys(items).length === 0) {
        return '<div class="text-muted small py-2"><em>No items found in this collection</em></div>';
    }
    
    let itemsHtml = '<div class="collection-items-list" style="max-height: 200px; overflow-y: auto;">';
    
    Object.values(items).forEach(item => {
        const displayTitle = escapeHtml(item.title || item.name || 'Unknown');
        const year = item.year ? ` (${item.year})` : '';
        const additionalInfo = [];

        if (item.artist && item.type !== 'show') {
            additionalInfo.push(`by ${escapeHtml(item.artist)}`);
        }
        if (item.album && item.type === 'track') {
            additionalInfo.push(`from ${escapeHtml(item.album)}`);
        }
        if (item.season_count && item.type === 'show') {
            additionalInfo.push(`${item.season_count} seasons`);
        }
        if (item.episode_count && item.type === 'show') {
            additionalInfo.push(`${item.episode_count} episodes`);
        }
        
        itemsHtml += `
            <div class="collection-item py-1 px-2 border-bottom" style="font-size: 0.8rem;">
                <div class="d-flex justify-content-between align-items-center">
                    <span class="item-title" title="${displayTitle}${year}">
                        ${displayTitle}${year}
                    </span>
                    <small class="text-muted">${item.type || ''}</small>
                </div>
                ${additionalInfo.length > 0 ? `
                    <div class="text-muted" style="font-size: 0.7rem;">
                        ${additionalInfo.join(' • ')}
                    </div>
                ` : ''}
                ${item.tagline ? `
                    <div class="text-muted" style="font-size: 0.7rem; font-style: italic;">
                        ${escapeHtml(item.tagline)}
                    </div>
                ` : ''}
            </div>
        `;
    });
    
    itemsHtml += '</div>';
    itemsHtml += `
        <div class="text-muted small mt-2 pt-2 border-top">
            <strong>Total: ${Object.keys(items).length} items</strong>
        </div>
    `;
    
    return itemsHtml;
}

async function expandCollection(expandedDiv, collectionKey, collectionType, buttonElement, collectionId) {
    try {
        expandedDiv.innerHTML = `
            <div class="text-muted small py-2">
                <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                Loading collection items...
            </div>
        `;
        expandedDiv.style.display = 'block';
        
        const response = await fetch('/get_collection_items', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': APP.csrfToken,
            },
            body: JSON.stringify({
                collection_key: collectionKey,
                collection_type: collectionType
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success' && data.items) {
            window.expandedCollections[collectionId] = {};
            data.items.forEach(item => {
                window.expandedCollections[collectionId][item.key || item.ratingKey] = item;
            });
            
            expandedDiv.innerHTML = buildCollectionItemsDisplay(window.expandedCollections[collectionId]);
            
            buttonElement.innerHTML = collectionToggleIcon(true);
            buttonElement.title = 'Hide collection items';
            
            updateSelectedItemsDisplay();
            debouncedUpdatePreview();                        
        } else {
            throw new Error(data.message || 'Failed to load collection items');
        }
    } catch (error) {
        console.error('Error loading collection items:', error);
        expandedDiv.innerHTML = `
            <div class="text-danger small py-2">
                <em>Error loading items: ${error.message}</em>
            </div>
        `;
    }
}

function updateSelectedItemsDisplay() {
    const container = document.getElementById('selected-items-list');
    
    if (selectedItems.length === 0) {
        container.innerHTML = '<div id="selected-items-empty" class="text-muted text-center py-3">No items selected. Use the buttons below to add items to your email.</div>';
    } else {
        let htmlContent = '';
        
        selectedItems.forEach((item, index) => {
            if (item.type === 'titleblock') {
                const currentContent = getTextBlockContent(item.id) || '';
                const badgeStyle = 'badge-warning';
                const placeholderText = 'Enter your title here...';
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded" 
                         data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge ${badgeStyle} me-2">${item.type}</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger title-remove remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        ${richTextToolbar(item.id)}
                        <div contenteditable="true" role="textbox" aria-multiline="true"
                            data-textblock-id="${item.id}"
                            class="form-control text-block-editor"
                            data-placeholder="${placeholderText}"
                            >${currentContent}</div>
                        ${textBlockStyleControls(index, item)}
                        <button type="button" class="nl-btn nl-btn--ghost nl-btn--sm mt-1 emoji-toggle-btn emoji-icon-btn" data-target="emoji-picker-${item.id}" title="Insert emoji into text block" aria-label="Insert emoji into text block">
                            <svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
                        </button>
                        <div id="emoji-picker-${item.id}" style="display: none; margin-top: 4px;">
                            <emoji-picker data-textblock-id="${item.id}" data-source="/static/js/vendor/emoji-picker-data.json" style="width: 100%; --emoji-size: 1.2rem; --num-columns: 10;"></emoji-picker>
                        </div>
                    </div>
                `;
            } else if (item.type === 'textblock' || item.type === 'headerblock') {
                const currentContent = getTextBlockContent(item.id) || '';
                const badgeStyle = item.type === 'headerblock' ? 'badge-warning' : 'badge-secondary';
                const placeholderText = item.type === 'headerblock' ? 'Enter your header here...' : 'Enter your text here...';
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded" 
                         data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge ${badgeStyle} me-2">${item.type}</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        ${richTextToolbar(item.id)}
                        <div contenteditable="true" role="textbox" aria-multiline="true"
                            data-textblock-id="${item.id}"
                            class="form-control text-block-editor"
                            data-placeholder="${placeholderText}"
                            >${currentContent}</div>
                        ${textBlockStyleControls(index, item)}
                        <button type="button" class="nl-btn nl-btn--ghost nl-btn--sm mt-1 emoji-toggle-btn emoji-icon-btn" data-target="emoji-picker-${item.id}" title="Insert emoji into text block" aria-label="Insert emoji into text block">
                            <svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
                        </button>
                        <div id="emoji-picker-${item.id}" style="display: none; margin-top: 4px;">
                            <emoji-picker data-textblock-id="${item.id}" data-source="/static/js/vendor/emoji-picker-data.json" style="width: 100%; --emoji-size: 1.2rem; --num-columns: 10;"></emoji-picker>
                        </div>
                    </div>
                `;
            } else if (item.type === 'separator') {
                htmlContent += `
                    <div class="selected-item d-flex align-items-center justify-content-between p-2 mb-2 border rounded"
                        data-index="${index}" draggable="false">
                        <span class="item-name" style="font-size: 0.9rem;">- Separator</span>
                        <div>
                            <span class="badge badge-secondary me-2">separator</span>
                            ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                        </div>
                    </div>
                `;
            } else if (item.type === 'image' || item.type === 'gif') {
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded"
                        data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="item-name">${item.type === 'gif' ? 'GIF' : 'Image/GIF'}</span>
                            <div>
                                <span class="badge badge-secondary me-2">${item.type}</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        ${item.src ? `<img src="${escapeHtml(item.src)}" style="max-height: 80px; max-width: 100%; object-fit: contain; margin-bottom: 8px; border-radius: 4px;">` : ''}
                        <div class="d-flex gap-2 align-items-center mb-2">
                            <input type="text" class="form-control form-control-sm media-src-input"
                                data-index="${index}"
                                placeholder="Image URL or upload a file..."
                                value="${escapeHtml(item.src || '')}"
                                style="flex: 1;">
                            <button type="button" class="nl-btn nl-btn--primary nl-btn--sm media-upload-btn" data-index="${index}" title="Upload from device" aria-label="Upload from device">
                                <svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                            </button>
                            <button type="button" class="nl-btn nl-btn--primary nl-btn--sm media-gif-search-btn" data-index="${index}" title="Search GIFs">
                                <svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> GIF
                            </button>
                        </div>
                        <div class="d-flex gap-2 align-items-center">
                            <label style="font-size: 0.8rem; white-space: nowrap;">Width (px):</label>
                            <input type="number" class="form-control form-control-sm media-width-input"
                                data-index="${index}" value="${item.width || 400}" style="width: 80px;">
                            <label style="font-size: 0.8rem;">Align:</label>
                            <select class="form-select form-select-sm media-align-select" data-index="${index}" style="width: 100px;">
                                <option value="left" ${item.align === 'left' ? 'selected' : ''}>Left</option>
                                <option value="center" ${item.align === 'center' ? 'selected' : ''}>Center</option>
                                <option value="right" ${item.align === 'right' ? 'selected' : ''}>Right</option>
                            </select>
                        </div>
                    </div>
                `;
            } else if (item.type === 'collection_group') {
                const currentTitle = item.title || 'Unnamed Collection Group';
                const collectionCount = item.collections ? item.collections.length : 0;
                const allGroupIds = selectedItems
                    .map((entry, entryIndex) => ({ entry, entryIndex }))
                    .filter(({ entry }) => entry && entry.type === 'collection_group')
                    .map(({ entry, entryIndex }) => ({
                        id: stableGroupIdFor(entry, entryIndex),
                        title: entry.title || 'Unnamed Collection Group'
                    }));
                
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded" 
                        data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center mb-2 snapin-item-head">
                            <input type="text"
                                class="form-control form-control-sm collection-group-title"
                                data-index="${index}"
                                value="${escapeHtml(currentTitle)}"
                                placeholder="Enter group name...">
                            <div class="snapin-item-actions">
                                <span class="badge badge-info">${collectionCount} collection(s)</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <div class="collection-group-items" style="font-size: 0.85rem;">
                            ${item.collections && item.collections.length > 0 
                                ? item.collections.map((col, i) => {
                                    const stableGroupId = stableGroupIdFor(item, index);
                                    const collectionId = collectionExpansionKey(stableGroupId, col.key);
                                    const isExpanded = window.expandedCollections[collectionId];
                                    const expandedItemsCount = isExpanded ? Object.keys(isExpanded).length : 0;
                                    
                                    return `
                                        <div class="collection-item-wrapper mb-2">
                                            <div class="d-flex justify-content-between align-items-center py-1 border-bottom">
                                                <div class="d-flex align-items-center">
                                                    <span>
                                                        ${escapeHtml(col.title)}
                                                        ${isExpanded 
                                                            ? `<small class="text-success">(showing ${expandedItemsCount} items)</small>`
                                                            : `(${col.childCount} items)`
                                                        }
                                                    </span>
                                                    <button type="button" 
                                                        class="btn btn-sm btn-outline-info me-2 expand-collection-btn" 
                                                        data-group-index="${stableGroupId}" 
                                                        data-collection-index="${i}"
                                                        data-collection-key="${col.key}"
                                                        data-collection-type="${col.type}"
                                                        data-collection-id="${collectionId}"
                                                        title="${isExpanded ? 'Hide collection items' : 'Show collection items'}"
                                                        style="padding: 0.1rem 0.4rem;">
                                                        ${collectionToggleIcon(isExpanded)}
                                                    </button>
                                                    ${isExpanded ? `
                                                    <button type="button" 
                                                        class="btn btn-sm btn-outline-secondary me-2 collapse-ui-collection-btn" 
                                                        data-group-index="${stableGroupId}" 
                                                        data-collection-index="${i}"
                                                        data-collection-id="${collectionId}"
                                                        title="${window.collapsedCollectionsUI[collectionId] ? 'Show items in snap-ins' : 'Hide items in snap-ins (keeps expanded in preview/email)'}"
                                                        style="font-size: 0.7rem; padding: 0.1rem 0.4rem;">
                                                        ${collectionPeekIcon(!!window.collapsedCollectionsUI[collectionId])}
                                                    </button>` : ""}
                                                </div>
                                                <button type="button" class="btn btn-sm btn-outline-danger remove-collection-btn"
                                                        data-group-index="${stableGroupId}" data-collection-index="${i}">x</button>
                                            </div>
                                            ${allGroupIds.length > 1 ? `
                                            <div class="collection-move-row">
                                                <label for="move-collection-${stableGroupId}-${i}">Move to</label>
                                                <select id="move-collection-${stableGroupId}-${i}"
                                                    class="form-select form-select-sm move-collection-select"
                                                    data-group-index="${stableGroupId}"
                                                    data-collection-index="${i}">
                                                    ${allGroupIds.map(g => `
                                                        <option value="${escapeHtml(g.id)}" ${g.id === stableGroupId ? 'selected' : ''}>
                                                            ${escapeHtml(g.title)}
                                                        </option>`).join('')}
                                                </select>
                                            </div>` : ''}
                                            <div class="collection-items-expanded" 
                                                id="collection-items-${stableGroupId}-${i}" 
                                                style="display: ${isExpanded && !window.collapsedCollectionsUI[collectionId] ? 'block' : 'none'}; margin-left: 20px; padding-left: 10px; border-left: 2px solid #007bff;">
                                                ${isExpanded 
                                                    ? buildCollectionItemsDisplay(isExpanded) 
                                                    : '<div class="text-muted small py-2"><em>Click the folder icon to load items...</em></div>'
                                                }
                                            </div>
                                        </div>
                                    `;
                                }).join('')
                                : '<em>No collections added yet</em>'
                            }
                        </div>
                    </div>
                `;
            } else if (item.type === 'random_pick') {
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded bg-light"
                         data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge badge-secondary me-2">${item.type}</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <div class="text-muted" style="font-size: 0.8rem;">A new random pick is drawn for each send; the preview shows a different pick than the send will.</div>
                        ${itemHeadingControls(index, item)}
                    </div>
                `;
            } else if (item.type === 'recently added' || item.type === 'most_watched' || item.type === 'recently_released') {
                // Per-library snap-ins stay editable after they are added: the
                // count set on the source row was previously frozen at add time.
                const isRA = item.type === 'recently added';
                const isRR = item.type === 'recently_released';
                const countValue = isRA ? (item.raCount || '') : (isRR ? (item.rrCount || '') : (item.mwCount || ''));
                const countLabel = isRA || isRR ? 'Items' : 'Titles';
                const orientation = isRR ? (item.rrOrientation || '') : (item.raOrientation || '');
                const heroChoices = (isRA && window.raItemsForLibrary) ? window.raItemsForLibrary(item.raLibrary) : [];
                const spotlight = (window.APP?.emailLayout || '') === 'spotlight';

                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded bg-light"
                         data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge badge-secondary me-2">${item.type}</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <div class="d-flex gap-2 align-items-center flex-wrap mt-2">
                            <label style="font-size: 0.8rem; white-space: nowrap;">${countLabel}:</label>
                            <input type="number" class="form-control form-control-sm snapin-count-input"
                                data-index="${index}" min="1" max="99" placeholder="all"
                                title="Blank uses the pulled item count"
                                value="${escapeHtml(String(countValue))}" style="width: 5em;">
                            ${(isRA || isRR) ? `
                            <label style="font-size: 0.8rem; white-space: nowrap;">Display:</label>
                            <select class="form-select form-select-sm ra-orientation-select" data-index="${index}" style="width: auto;">
                                <option value=""     ${orientation === ''      ? 'selected' : ''}>Layout default</option>
                                <option value="grid" ${orientation === 'grid'  ? 'selected' : ''}>Horizontal grid</option>
                                <option value="list" ${orientation === 'list'  ? 'selected' : ''}>Vertical list</option>
                            </select>` : ''}
                        </div>
                        ${(isRA && spotlight) ? `
                        <div class="d-flex gap-2 align-items-center flex-wrap mt-2">
                            <label style="font-size: 0.8rem; white-space: nowrap;">Spotlight feature:</label>
                            <select class="form-select form-select-sm ra-hero-select" data-index="${index}" style="max-width: 260px;">
                                <option value="">First item (newest)</option>
                                ${heroChoices.map(choice => `
                                    <option value="${escapeHtml(choice.key)}" ${String(item.raHero || '') === choice.key ? 'selected' : ''}>
                                        ${escapeHtml(choice.title)}${choice.year ? ` (${escapeHtml(String(choice.year))})` : ''}
                                    </option>`).join('')}
                            </select>
                        </div>` : ''}
                        ${itemHeadingControls(index, item)}
                    </div>
                `;
            } else if (item.type === 'sonarr_coming_soon' || item.type === 'radarr_coming_soon') {
                // The calendar and agenda views reflow to a stacked list on
                // narrow screens; the poster grid keeps its own columns.
                const csView = item.csView || '';
                const csCount = item.csCount || '';
                // Seasons only exist for TV, so the kind filter is Sonarr-only.
                const isTv = item.type === 'sonarr_coming_soon';
                const csKind = item.csKind || '';

                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded bg-light"
                         data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge badge-secondary me-2">${item.type}</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <div class="d-flex gap-2 align-items-center flex-wrap mt-2">
                            <label style="font-size: 0.8rem; white-space: nowrap;">Display:</label>
                            <select class="form-select form-select-sm cs-view-select" data-index="${index}" style="width: auto;">
                                <option value=""         ${csView === ''         ? 'selected' : ''}>Layout default</option>
                                <option value="grid"     ${csView === 'grid'     ? 'selected' : ''}>Poster grid</option>
                                <option value="calendar" ${csView === 'calendar' ? 'selected' : ''}>Calendar</option>
                                <option value="agenda"   ${csView === 'agenda'   ? 'selected' : ''}>Agenda</option>
                            </select>
                            <label style="font-size: 0.8rem; white-space: nowrap;">Limit:</label>
                            <input type="number" class="form-control form-control-sm cs-count-input"
                                data-index="${index}" min="1" max="99" placeholder="all"
                                title="Most entries to show. Blank shows everything in the window."
                                value="${escapeHtml(String(csCount))}" style="width: 5em;">
                        </div>
                        ${isTv ? `
                        <div class="d-flex gap-2 align-items-center flex-wrap mt-2">
                            <label style="font-size: 0.8rem; white-space: nowrap;">Include:</label>
                            <select class="form-select form-select-sm cs-kind-select" data-index="${index}" style="width: auto;">
                                <option value=""           ${csKind === ''           ? 'selected' : ''}>Every episode</option>
                                <option value="premieres"  ${csKind === 'premieres'  ? 'selected' : ''}>Premieres only (new and returning)</option>
                                <option value="new-series" ${csKind === 'new-series' ? 'selected' : ''}>New series only</option>
                            </select>
                        </div>` : ''}
                        ${itemHeadingControls(index, item)}
                    </div>
                `;
            } else {
                const headingControls = itemHeadingControls(index, item);
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded bg-light"
                         data-index="${index}" draggable="false">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge badge-secondary me-2">${item.type}</span>
                                ${itemMoveControls(index, selectedItems.length)}<button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        ${headingControls}
                    </div>
                `;
            }
        });
        
        container.innerHTML = htmlContent;

        document.querySelectorAll('.collection-group-title').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (selectedItems[index] && selectedItems[index].type === 'collection_group') {
                    selectedItems[index].title = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });
        
        document.querySelectorAll('.remove-collection-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const stableGroupId = e.currentTarget.dataset.groupIndex;
                const groupIndex = findGroupIndexByStableId(stableGroupId);
                const collectionIndex = parseInt(e.currentTarget.dataset.collectionIndex);

                if (selectedItems[groupIndex] && selectedItems[groupIndex].collections) {
                    const collection = selectedItems[groupIndex].collections[collectionIndex];
                    const collectionId = collectionExpansionKey(stableGroupId, collection.key);
                    delete window.expandedCollections[collectionId];
                    delete window.collapsedCollectionsUI[collectionId];

                    selectedItems[groupIndex].collections.splice(collectionIndex, 1);
                    updateSelectedItemsDisplay();
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.move-collection-select').forEach(select => {
            select.addEventListener('change', (e) => {
                const fromGroupId = e.currentTarget.dataset.groupIndex;
                const collectionIndex = parseInt(e.currentTarget.dataset.collectionIndex);
                const toGroupId = e.currentTarget.value;
                if (!moveCollectionToGroup(fromGroupId, collectionIndex, toGroupId)) {
                    e.currentTarget.value = fromGroupId;
                }
            });
        });

        document.querySelectorAll('.expand-collection-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const stableGroupId = e.currentTarget.dataset.groupIndex;
                const collectionIndex = parseInt(e.currentTarget.dataset.collectionIndex);
                const collectionKey = e.currentTarget.dataset.collectionKey;
                const collectionType = e.currentTarget.dataset.collectionType;
                const collectionId = e.currentTarget.dataset.collectionId;

                const expandedDiv = document.getElementById(`collection-items-${stableGroupId}-${collectionIndex}`);
                const isCurrentlyExpanded = window.expandedCollections[collectionId];

                if (!isCurrentlyExpanded) {
                    await expandCollection(expandedDiv, collectionKey, collectionType, btn, collectionId);
                } else {
                    delete window.expandedCollections[collectionId];
                    delete window.collapsedCollectionsUI[collectionId];
                    expandedDiv.style.display = 'none';
                    btn.innerHTML = collectionToggleIcon(false);
                    btn.title = 'Show collection items';

                    updateSelectedItemsDisplay();
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll(".collapse-ui-collection-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const target = e.currentTarget;
                const stableGroupId = target.dataset.groupIndex;
                const collectionIndex = parseInt(target.dataset.collectionIndex);
                const collectionId = target.dataset.collectionId;

                const expandedDiv = document.getElementById(`collection-items-${stableGroupId}-${collectionIndex}`);
                const nowCollapsed = !window.collapsedCollectionsUI[collectionId];

                if (nowCollapsed) {
                    window.collapsedCollectionsUI[collectionId] = true;
                    expandedDiv.style.display = "none";
                } else {
                    delete window.collapsedCollectionsUI[collectionId];
                    expandedDiv.style.display = "block";
                }
                target.innerHTML = collectionPeekIcon(nowCollapsed);
                target.title = nowCollapsed
                    ? "Show items in snap-ins"
                    : "Hide items in snap-ins (keeps expanded in preview/email)";
            });
        });

        document.querySelectorAll('.media-src-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].src = e.target.value.trim();
                    if (selectedItems[index].src.toLowerCase().includes('.gif') || selectedItems[index].src.includes('klipy')) {
                        selectedItems[index].type = 'gif';
                    }
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.media-width-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].width = parseInt(e.target.value) || 400;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.media-align-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].align = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.snapin-count-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                const target = selectedItems[index];
                if (!target) return;
                const key = { 'recently added': 'raCount',
                              'recently_released': 'rrCount' }[target.type] || 'mwCount';
                const count = parseInt(e.target.value, 10);
                if (count > 0) {
                    target[key] = count;
                } else {
                    delete target[key];
                }
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.ra-orientation-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                const target = selectedItems[index];
                if (!target) return;
                const key = target.type === 'recently_released' ? 'rrOrientation' : 'raOrientation';
                if (e.currentTarget.value) {
                    target[key] = e.currentTarget.value;
                } else {
                    delete target[key];
                }
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.text-block-font').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                if (e.currentTarget.value) selectedItems[index].fontFamily = e.currentTarget.value;
                else delete selectedItems[index].fontFamily;
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.text-block-size').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                const size = parseInt(e.currentTarget.value, 10);
                if (size >= 8 && size <= 96) selectedItems[index].fontSize = size;
                else delete selectedItems[index].fontSize;
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.snapin-heading-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                const value = e.currentTarget.value;
                if (value.trim()) selectedItems[index].heading = value;
                else delete selectedItems[index].heading;
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.snapin-heading-hide').forEach(box => {
            box.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                if (e.currentTarget.checked) selectedItems[index].hideHeading = true;
                else delete selectedItems[index].hideHeading;
                // Re-render so the text field's disabled state follows.
                updateSelectedItemsDisplay();
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.cs-view-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                if (e.target.value) {
                    selectedItems[index].csView = e.target.value;
                } else {
                    delete selectedItems[index].csView;
                }
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.cs-count-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                const count = parseInt(e.currentTarget.value, 10);
                if (Number.isNaN(count) || count < 1) delete selectedItems[index].csCount;
                else selectedItems[index].csCount = count;
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.cs-kind-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                if (e.currentTarget.value) selectedItems[index].csKind = e.currentTarget.value;
                else delete selectedItems[index].csKind;
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.ra-hero-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (!selectedItems[index]) return;
                if (e.target.value) {
                    selectedItems[index].raHero = e.target.value;
                } else {
                    delete selectedItems[index].raHero;
                }
                debouncedUpdatePreview();
            });
        });

        document.querySelectorAll('.emoji-content-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].content = e.target.value;
                    selectedItems[index].name = `${e.target.value || 'Emoji'}`;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.emoji-size-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].size = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.emoji-align-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].align = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.media-upload-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                const input = document.getElementById('media-upload-input');
                input.dataset.targetIndex = index;
                input.click();
            });
        });

        document.querySelectorAll('.media-gif-search-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.currentTarget.dataset.index);
                openGifPicker(index);
            });
        });

        document.querySelectorAll('.emoji-toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const targetId = btn.dataset.target;
                const container = document.getElementById(targetId);
                if (!container) return;
                const isVisible = container.style.display !== 'none';
                document.querySelectorAll('[id^="emoji-picker-"]').forEach(el => {
                    if (el.tagName !== 'EMOJI-PICKER') el.style.display = 'none';
                });
                container.style.display = isVisible ? 'none' : 'block';
            });
        });

        document.querySelectorAll('emoji-picker').forEach(picker => {
            picker.addEventListener('emoji-click', (e) => {
                const emoji = e.detail.unicode;
                const textblockId = picker.dataset.textblockId;
                const textarea = document.querySelector(`[data-textblock-id="${textblockId}"]`);
                if (!textarea) return;

                const start = textarea.selectionStart ?? textarea.value.length;
                const end = textarea.selectionEnd ?? textarea.value.length;
                textarea.value = textarea.value.slice(0, start) + emoji + textarea.value.slice(end);

                const newPos = start + emoji.length;
                textarea.setSelectionRange(newPos, newPos);
                textarea.focus();

                setTextBlockContent(textblockId, textarea.value);
                debouncedUpdatePreview();

                const container = document.getElementById(`emoji-picker-${textblockId}`);
                if (container) container.style.display = 'none';
            });
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.emoji-toggle-btn') && !e.target.closest('[id^="emoji-picker-"]')) {
                document.querySelectorAll('[id^="emoji-picker-"]').forEach(el => {
                    if (el.tagName !== 'EMOJI-PICKER') el.style.display = 'none';
                });
            }
        });
        
        setupDragAndDrop();
    }

    if (typeof refreshCollectionTargetOptions === 'function') refreshCollectionTargetOptions();

    updatePreview();
}

function captureChartAsBase64(chartId) {
    const chart = Highcharts.charts.find(c => c && c.renderTo.id === chartId);
    if (!chart) {
        console.log('Chart not found for ID:', chartId);
        return null;
    }
    
    try {
        const svg = chart.getSVG({
            width: 600,
            height: 400
        });
        
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 600;
        canvas.height = 400;
        
        const img = new Image();
        const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(svgBlob);
        
        return new Promise((resolve) => {
            img.onload = function() {
                ctx.drawImage(img, 0, 0);
                const dataUrl = canvas.toDataURL('image/png');
                URL.revokeObjectURL(url);
                resolve(dataUrl);
            };
            img.onerror = function() {
                console.error('Failed to load chart image');
                URL.revokeObjectURL(url);
                resolve(null);
            };
            img.src = url;
        });
    } catch (error) {
        console.error('Error capturing chart:', error);
        return null;
    }
}

// Single source for the builder's chart config. Called on add, on template
// load, and again after every stats pull, so the instance in #graph-N always
// reflects the current graphDataList rather than whatever it was first drawn
// with. Returns false when the index has no data to draw.
function renderGraphChart(id) {
    const index = parseInt(id.split('-')[1], 10);
    const graphData = graphDataList[index];
    const commandInfo = graphCommands[index];

    if (!graphData || !commandInfo) {
        console.warn('No graph data available for', id);
        return false;
    }

    try {
        loadIBMPlexSans();

        Highcharts.chart(id, {
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

        renderedCharts.add(id);
        applyChartTheme(document.documentElement.classList.contains('dark'));
        return true;
    } catch (err) {
        console.warn('Failed to render graph', id, err);
        return false;
    }
}

// Refresh item.chartImage when it is missing or was captured from older data.
// That PNG is what actually ships (app/emails/blocks.py attaches it), so this
// runs before every preview and every send instead of once at add time. The
// generation check keeps a settled chart from being re-captured on each
// keystroke while still guaranteeing a re-capture after a pull.
async function ensureChartImage(item) {
    if (item.chartImage && item.chartGen === chartDataGeneration) return;

    if (!renderedCharts.has(item.id) || item.chartGen !== chartDataGeneration) {
        if (!renderGraphChart(item.id)) return;
        // Highcharts needs a beat before getSVG() reflects the new series
        await new Promise(resolve => setTimeout(resolve, 500));
    }

    const chartImage = await captureChartAsBase64(item.id);
    if (chartImage) {
        item.chartImage = chartImage;
        item.chartGen = chartDataGeneration;
    }
}

function loadIBMPlexSans() {
    if (!document.querySelector('link[href*="IBM+Plex+Sans"]')) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://fonts.googleapis.com/css?family=IBM+Plex+Sans:400,700&display=swap';
        document.head.appendChild(link);
    }
}

async function addItemWithChartCapture(id, name, type, extra = {}) {
    if (!id || !type) {
        console.warn('addItem aborted: missing id/type', { id, type, name, extra });
        return false;
    }

    if (selectedItems.some(it => it.id === id && it.type === type)) {
        console.log('Item already added:', { id, type });
        return false;
    }

    const item = { id, name: name || id, type, ...extra };

    if (type === 'graph') {
        console.log('Capturing chart for:', id);

        await ensureChartImage(item);

        if (item.chartImage) {
            console.log('Successfully captured chart image for:', id);
        } else {
            console.warn('Failed to capture chart image for:', id);
        }
    }

    selectedItems.push(item);

    updateSelectedItemsDisplay();
    return true;
}

function addItem(id, name, type, extra = {}) {
    if (!id || !type) {
        console.warn('addItem aborted: missing id/type', { id, type, name, extra });
        return false;
    }

    if (selectedItems.some(it => it.id === id && it.type === type)) {
        console.log('Item already added:', { id, type });
        return false;
    }

    // No capture here: the sync path leaves item.chartImage unset so the next
    // preview or send fills it in from current data via ensureChartImage.
    if (type === 'graph' && !renderedCharts.has(id)) {
        renderGraphChart(id);
    }

    const item = { id, name: name || id, type, ...extra };

    selectedItems.push(item);

    updateSelectedItemsDisplay();
    return true;
}

function removeItem(index) {
    const removedItem = selectedItems[index];
    selectedItems.splice(index, 1);
    updateSelectedItemsDisplay();
    
    const button = document.querySelector(`[data-id="${removedItem.id}"]`);
    if (button) {
        button.textContent = `Add`;
        button.classList.remove('nl-btn--success');
        button.classList.add('nl-btn--primary');
        button.disabled = false;
    }
}

const DRAG_EXEMPT_SELECTOR = 'input, textarea, select, button, a, [contenteditable="true"], emoji-picker';

const DRAG_SCROLL_ZONE_PX = 48;   // edge band that triggers a scroll
const DRAG_SCROLL_MAX_PX = 18;    // per-frame step at the very edge

function scrollableAncestor(el) {
    for (let node = el && el.parentElement; node; node = node.parentElement) {
        const overflowY = window.getComputedStyle(node).overflowY;
        if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) {
            return node;
        }
    }
    return document.scrollingElement || document.documentElement;
}

function makeDragScroller() {
    let container = null;
    let velocity = 0;
    let frame = null;

    function step() {
        frame = null;
        if (!container || !velocity) return;
        if (container === document.scrollingElement || container === document.documentElement) {
            window.scrollBy(0, velocity);
        } else {
            container.scrollTop += velocity;
        }
        frame = window.requestAnimationFrame(step);
    }

    return {
        start(el) {
            container = scrollableAncestor(el);
            velocity = 0;
        },
        // Ramps from 0 at the inner edge of the band to the full step at the
        // boundary, so a slow approach nudges and parking at the edge flies.
        update(clientY) {
            if (!container) return;
            const isPage = container === document.scrollingElement || container === document.documentElement;
            const rect = isPage
                ? { top: 0, bottom: window.innerHeight }
                : container.getBoundingClientRect();

            const fromTop = clientY - rect.top;
            const fromBottom = rect.bottom - clientY;

            if (fromTop < DRAG_SCROLL_ZONE_PX) {
                const ratio = Math.min(1, (DRAG_SCROLL_ZONE_PX - fromTop) / DRAG_SCROLL_ZONE_PX);
                velocity = -Math.ceil(ratio * DRAG_SCROLL_MAX_PX);
            } else if (fromBottom < DRAG_SCROLL_ZONE_PX) {
                const ratio = Math.min(1, (DRAG_SCROLL_ZONE_PX - fromBottom) / DRAG_SCROLL_ZONE_PX);
                velocity = Math.ceil(ratio * DRAG_SCROLL_MAX_PX);
            } else {
                velocity = 0;
            }

            if (velocity && frame === null) frame = window.requestAnimationFrame(step);
        },
        stop() {
            if (frame !== null) window.cancelAnimationFrame(frame);
            frame = null;
            container = null;
            velocity = 0;
        }
    };
}

const dragScroller = makeDragScroller();

function moveItemToEdge(index, edge) {
    if (index < 0 || index >= selectedItems.length) return;
    if (edge === 'top' && index === 0) return;
    if (edge === 'bottom' && index === selectedItems.length - 1) return;

    const [moved] = selectedItems.splice(index, 1);
    if (edge === 'top') {
        selectedItems.unshift(moved);
    } else {
        selectedItems.push(moved);
    }
    updateSelectedItemsDisplay();
    debouncedUpdatePreview();
}

function setupDragAndDrop() {
    const items = () => Array.from(document.querySelectorAll('.selected-item'));
    const indexOfEl = (el) => allItems().indexOf(el);
    let draggedElement = null;

    items().forEach((item, index) => {
        item.addEventListener('mousedown', (e) => {
            item.draggable = !(e.target.closest && e.target.closest(DRAG_EXEMPT_SELECTOR));
        });

        item.addEventListener('mouseup', () => {
            item.draggable = false;
        });

        item.addEventListener('dragstart', (e) => {
            draggedElement = item;
            e.dataTransfer.setData('text/plain', index);
            e.dataTransfer.effectAllowed = 'move';
            dragScroller.start(item);

            setTimeout(() => {
                item.classList.add('dragging');
            }, 0);
        });

        item.addEventListener('dragend', () => {
            item.draggable = false;
            item.classList.remove('dragging');
            items().forEach(i => i.classList.remove('drag-over'));
            draggedElement = null;
            dragScroller.stop();
        });
        
        item.addEventListener('dragenter', (e) => {
            e.preventDefault();
            if (draggedElement && draggedElement !== item) {
                item.classList.add('drag-over');
            }
        });
        
        item.addEventListener('dragleave', (e) => {
            if (!item.contains(e.relatedTarget)) {
                item.classList.remove('drag-over');
            }
        });
        
        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            dragScroller.update(e.clientY);
        });

        item.addEventListener('drop', (e) => {
            e.preventDefault();
            item.classList.remove('drag-over');
            dragScroller.stop();

            const draggedIndex = parseInt(e.dataTransfer.getData('text/plain'));
            const targetIndex = parseInt(item.dataset.index);
            
            if (draggedIndex !== targetIndex) {
                const draggedItem = selectedItems[draggedIndex];
                selectedItems.splice(draggedIndex, 1);
                selectedItems.splice(targetIndex, 0, draggedItem);
                updateSelectedItemsDisplay();
            }
        });
    });

    const container = document.getElementById('selected-items-list');
    if (container && !container.dataset.dragScrollBound) {
        container.dataset.dragScrollBound = '1';
        container.addEventListener('dragover', (e) => {
            e.preventDefault();
            dragScroller.update(e.clientY);
        });
        container.addEventListener('drop', () => dragScroller.stop());
    }
}

let textBlockCounter = 0;
let titleBlockCounter = 0;
let headerBlockCounter = 0;
let mediaBlockCounter = 0;

function createTextBlock(blockType = 'text') {
    textBlockCounter++;
    const textBlockId = `text-block-${textBlockCounter}`;
    let displayName = 'New text block';

    let textContent = '';
    if (blockType === 'html-link') {
        textContent = `<a href="https://www.google.com" target="_blank">Click to go to Google</a>`;
        displayName = 'HTML Link';
    }
    
    if (addItem(textBlockId, displayName, 'textblock')) {
        setTextBlockContent(textBlockId, textContent);
        debouncedUpdatePreview();
        return textBlockId;
    }
    return null;
}

function textBlockSurface(textBlockId) {
    return document.querySelector(`[data-textblock-id="${CSS.escape(textBlockId)}"].text-block-editor`);
}

function getTextBlockContent(textBlockId) {
    const surface = textBlockSurface(textBlockId);
    if (surface) {
        if (surface.tagName === 'TEXTAREA') return surface.value;
        // The contenteditable surface can pick up the editor's own font-size
        // when the browser rewrites nodes; that must not ship in the email.
        const html = surface.innerHTML;
        return (typeof stripEditorArtifacts === 'function') ? stripEditorArtifacts(html) : html;
    }
    const item = selectedItems.find(item => item.id === textBlockId);
    return (item && typeof item.content === 'string') ? item.content : '';
}

function setTextBlockContent(textBlockId, content) {
    const surface = textBlockSurface(textBlockId);
    if (surface) {
        if (surface.tagName === 'TEXTAREA') surface.value = content;
        else surface.innerHTML = content;
    }
    const index = selectedItems.findIndex(item => item.id === textBlockId);
    if (index !== -1) {
        selectedItems[index].content = content;
        selectedItems[index].name = getTextBlockDisplayName(content);
        const nameSpan = document.querySelector(`[data-index="${index}"] .item-name`);
        if (nameSpan) {
            nameSpan.textContent = selectedItems[index].name;
        }
    }
}

function textBlockPlainText(content) {
    const html = String(content ?? '');
    if (html.indexOf('<') === -1 && html.indexOf('&') === -1) return html;
    const scratch = document.createElement('div');
    scratch.innerHTML = html;
    // <br> and block boundaries read as line breaks in the label.
    scratch.querySelectorAll('br, div, p, li').forEach(el => el.insertAdjacentText('beforebegin', '\n'));
    return (scratch.textContent || '').replace(/ /g, ' ');
}

function getTextBlockDisplayName(content) {
    const text = textBlockPlainText(content);
    const firstLine = (text.split('\n').find(line => line.trim().length) || '').trim();
    if (firstLine.length === 0) {
        // Markup with no text of its own is still worth distinguishing from
        // an untouched block.
        return String(content ?? '').trim() ? 'HTML block' : 'Empty text block';
    }
    return firstLine.length > 30 ? firstLine.substring(0, 30) + '...' : firstLine;
}

function updateTextBlockName(textBlockId, index) {
    const content = getTextBlockContent(textBlockId);
    const newName = getTextBlockDisplayName(content);
    
    if (selectedItems[index]) {
        selectedItems[index].content = content;
        selectedItems[index].name = newName;

        const nameSpan = document.querySelector(`[data-index="${index}"] .item-name`);
        if (nameSpan) {
            nameSpan.textContent = newName;
        }
    }
    
    clearTimeout(window.previewUpdateTimeout);
    window.previewUpdateTimeout = setTimeout(updatePreview, 300);
}

function createSeparatorBlock() {
    textBlockCounter++;
    const id = `separator-block-${textBlockCounter}`;
    addItem(id, '  Separator', 'separator');
}

function createIntroBlock() {
    textBlockCounter++;
    const textBlockId = `intro-block-${textBlockCounter}`;
    const serverName = APP.serverName;
    const introContent = APP.defaultIntroText || `You are receiving this email because you are a member of ${serverName}.`;
    const displayName = 'Intro: Member message';
    
    if (addItem(textBlockId, displayName, 'textblock')) {
        setTextBlockContent(textBlockId, introContent);
        debouncedUpdatePreview();
        return textBlockId;
    }
    return null;
}

function createOutroBlock() {
    textBlockCounter++;
    const textBlockId = `outro-block-${textBlockCounter}`;
    const outroContent = APP.defaultOutroText || 'Thanks for using Plex and for reading this newsletterr email!';
    const displayName = 'Outro: Thank you message';
    
    if (addItem(textBlockId, displayName, 'textblock')) {
        setTextBlockContent(textBlockId, outroContent);
        debouncedUpdatePreview();
        return textBlockId;
    }
    return null;
}

function createTitleBlock() {
    if (titleBlockCounter > 0) {
        return null;
    } else {
        titleBlockCounter++;
        const textBlockId = `title-block-${titleBlockCounter}`;
        const titleContent = 'Newsletter Title';
        const displayName = 'Title: Newsletter Title';
        
        if (addItem(textBlockId, displayName, 'titleblock')) {
            setTextBlockContent(textBlockId, titleContent);
            debouncedUpdatePreview();
            return textBlockId;
        }
        return null;
    }
}

function createHeaderBlock() {
    headerBlockCounter++;
    const textBlockId = `header-block-${headerBlockCounter}`;
    const headerContent = 'Newsletter Header';
    const displayName = 'Header: Newsletter Header';
    
    if (addItem(textBlockId, displayName, 'headerblock')) {
        setTextBlockContent(textBlockId, headerContent);
        debouncedUpdatePreview();
        return textBlockId;
    }
    return null;
}

function createImageBlock(src = '', isUpload = false) {
    mediaBlockCounter++;
    const id = `image-block-${mediaBlockCounter}`;
    const item = { id, name: 'Image/GIF', type: 'image', src, width: 400, align: 'center', isUpload };
    selectedItems.push(item);
    updateSelectedItemsDisplay();
}

// Delegated replacement for the old inline oninput= on text block editors,
// which enforcing CSP blocks (no inline handlers).
document.addEventListener('input', (e) => {
    const editor = e.target.closest('.text-block-editor');
    if (!editor) return;
    const wrapper = editor.closest('.selected-item');
    const index = wrapper ? parseInt(wrapper.dataset.index, 10) : NaN;
    if (!Number.isNaN(index)) {
        updateTextBlockName(editor.dataset.textblockId, index);
    }
});

document.addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;

    if (btn.id === 'add-text-block-btn') { createTextBlock(); return; }
    if (btn.id === 'add-separator-btn') { createSeparatorBlock(); return; }
    if (btn.id === 'add-html-text-block-btn') { createTextBlock(blockType = 'html-link'); return; }
    if (btn.id === 'add-intro-btn') { createIntroBlock(); return; }
    if (btn.id === 'add-outro-btn') { createOutroBlock(); return; }
    if (btn.id === 'add-title-btn') { createTitleBlock(); return; }
    if (btn.id === 'add-header-btn') { createHeaderBlock(); return; }
    if (btn.id === 'add-image-btn') { createImageBlock(); return; }

    if (btn.classList.contains('remove-item-btn')) {
        const index = parseInt(btn.dataset.index, 10);
        if (!Number.isNaN(index)) removeItem(index);
        if (btn.classList.contains('title-remove')) { titleBlockCounter = 0; }
        return;
    }

    if (btn.classList.contains('item-move-btn')) {
        const index = parseInt(btn.dataset.index, 10);
        if (!Number.isNaN(index)) moveItemToEdge(index, btn.dataset.edge);
        return;
    }

    const isAdd =
        btn.classList.contains('add-stat-btn') ||
        btn.classList.contains('add-graph-btn') ||
        btn.classList.contains('ra-add-btn') ||
        btn.classList.contains('rr-add-btn') ||
        btn.classList.contains('mw-add-btn') ||
        btn.classList.contains('recs-add-btn') ||
        btn.classList.contains('droppedneedle-add-btn') ||
        btn.classList.contains('droppedneedle-server-add-btn') ||
        btn.classList.contains('yearly-wrapped-add-btn') ||
        btn.classList.contains('sonarr-coming-soon-add-btn') ||
        btn.classList.contains('radarr-coming-soon-add-btn') ||
        btn.classList.contains('ombi-requests-add-btn') ||
        btn.classList.contains('seerr-requests-add-btn') ||
        btn.classList.contains('top-viewer-add-btn') ||
        btn.classList.contains('featured-pick-add-btn');

    if (!isAdd) return;

    let { id, name, type } = btn.dataset;
    if (!id || !type) return;

    console.log('Adding item:', { id, name, type });
    console.log('Current selectedItems before:', selectedItems);

    const extra = {};
    if (type === 'recently added' && btn.dataset.lib) {
        extra.raLibrary = btn.dataset.lib;
        const raCount = parseInt(btn.closest('.snapin-row')?.querySelector('.ra-count-input')?.value, 10);
        if (raCount > 0) extra.raCount = raCount;
    }
    if (type === 'recently_released' && btn.dataset.lib) {
        extra.rrLibrary = btn.dataset.lib;
        const rrCount = parseInt(btn.closest('.snapin-row')?.querySelector('.rr-count-input')?.value, 10);
        if (rrCount > 0) extra.rrCount = rrCount;
    }
    if (type === 'most_watched' && btn.dataset.lib) {
        extra.mwLibrary = btn.dataset.lib;
        const mwRow = btn.closest('.snapin-row');
        const mwCount = parseInt(mwRow?.querySelector('.mw-count-input')?.value, 10);
        if (mwCount > 0) extra.mwCount = mwCount;
        const mwScope = mwRow?.querySelector('.mw-scope-select')?.value || '';
        if (mwScope) {
            // distinct id/name so the all-time and pull-range variants of one
            // library can both be added
            extra.mwScope = mwScope;
            id = `${id}-recent`;
            name = `${name} (pull range)`;
        }
    }
    if (type === 'featured_pick' && btn.dataset.ratingKey) {
        extra.ratingKey = btn.dataset.ratingKey;
    }
    if (type === 'recommendations' || type === 'droppedneedle_wrapped') {
        if (btn.dataset.userKey) extra.userKey = btn.dataset.userKey;
    }
    if (type === 'graph') {
        btn.textContent = 'Capturing...';
        btn.disabled = true;
    }

    if (await addItemWithChartCapture(id, name || id, type, extra)) {
        btn.textContent = 'Added';
        btn.classList.remove('nl-btn--primary');
        btn.classList.add('nl-btn--success');
        btn.disabled = true;

        console.log('Item added. Current selectedItems:', selectedItems);
    } else {
        if (type === 'graph') {
            btn.textContent = 'Add';
            btn.disabled = false;
        }
        console.log('Item already exists');
    }
});

updateSelectedItemsDisplay();
