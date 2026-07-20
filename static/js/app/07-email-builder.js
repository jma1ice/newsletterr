window.expandedCollections = {};
window.collapsedCollectionsUI = {};

// Chevron for the collection expand/collapse toggle: points down when the
// collection is expanded, right when collapsed (matches the cache/BCC cards).
function collectionToggleIcon(expanded) {
    const points = expanded ? '6 9 12 15 18 9' : '9 6 15 12 9 18';
    return `<svg class="nl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polyline points="${points}"/></svg>`;
}

function convertExpandedCollectionsForBackend() {
    const convertedCollections = {};
    
    console.log('Converting expanded collections:', window.expandedCollections);
    console.log('Selected items:', selectedItems);
    
    for (const [stableCollectionId, items] of Object.entries(window.expandedCollections)) {
        console.log('Processing collection ID:', stableCollectionId);
        
        const parts = stableCollectionId.split('-');
        
        if (parts.length >= 3) {
            let groupArrayIndex = -1;
            let collectionIndex, collectionKey;
            
            if (parts[0] === 'collection' && parts[1] === 'group' && parts.length >= 5) {
                const stableGroupId = `${parts[0]}-${parts[1]}-${parts[2]}`;
                collectionIndex = parts[3];
                collectionKey = parts.slice(4).join('-');
                
                console.log('Parsed stable group format:', {stableGroupId, collectionIndex, collectionKey});
                
                for (let i = 0; i < selectedItems.length; i++) {
                    if (selectedItems[i] && selectedItems[i].type === 'collection_group' && selectedItems[i].id === stableGroupId) {
                        groupArrayIndex = i;
                        break;
                    }
                }
            } else if (parts[0] === 'group' && parts.length >= 4) {
                groupArrayIndex = parseInt(parts[1]);
                collectionIndex = parts[2];
                collectionKey = parts.slice(3).join('-');
                
                console.log('Parsed group format:', {groupArrayIndex, collectionIndex, collectionKey});
            }
            
            if (groupArrayIndex !== -1 && collectionIndex !== undefined) {
                const backendCollectionId = `${groupArrayIndex}-${collectionIndex}-${collectionKey}`;
                convertedCollections[backendCollectionId] = items;
                console.log('Converted:', stableCollectionId, '→', backendCollectionId);
            } else {
                console.warn('Failed to convert collection ID:', stableCollectionId);
            }
        }
    }
    
    console.log('Final converted collections:', convertedCollections);
    return convertedCollections;
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
                         data-index="${index}" draggable="true">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge ${badgeStyle} me-2">${item.type}</span>
                                <button type="button" class="btn btn-sm btn-outline-danger title-remove remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <textarea 
                            data-textblock-id="${item.id}" 
                            class="form-control text-block-editor" 
                            style="height: 60px; font-size: 0.9rem; resize: vertical;"
                            placeholder="${placeholderText}"
                            >${escapeHtml(currentContent)}</textarea>
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
                         data-index="${index}" draggable="true">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge ${badgeStyle} me-2">${item.type}</span>
                                <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <textarea 
                            data-textblock-id="${item.id}" 
                            class="form-control text-block-editor" 
                            style="height: 60px; font-size: 0.9rem; resize: vertical;"
                            placeholder="${placeholderText}"
                            >${escapeHtml(currentContent)}</textarea>
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
                        data-index="${index}" draggable="true">
                        <span class="item-name" style="font-size: 0.9rem;">- Separator</span>
                        <div>
                            <span class="badge badge-secondary me-2">separator</span>
                            <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                        </div>
                    </div>
                `;
            } else if (item.type === 'image' || item.type === 'gif') {
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded"
                        data-index="${index}" draggable="true">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span class="item-name">${item.type === 'gif' ? 'GIF' : 'Image/GIF'}</span>
                            <div>
                                <span class="badge badge-secondary me-2">${item.type}</span>
                                <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
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
                
                htmlContent += `
                    <div class="selected-item d-flex flex-column p-2 mb-2 border rounded" 
                        data-index="${index}" draggable="true">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <input type="text" 
                                class="form-control form-control-sm collection-group-title" 
                                data-index="${index}"
                                value="${escapeHtml(currentTitle)}"
                                placeholder="Enter group name..."
                                style="max-width: 300px;">
                            <div>
                                <span class="badge badge-info me-2">${collectionCount} collection(s)</span>
                                <span class="badge badge-secondary me-2">collection group</span>
                                <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <div class="collection-group-items" style="font-size: 0.85rem;">
                            ${item.collections && item.collections.length > 0 
                                ? item.collections.map((col, i) => {
                                    const stableGroupId = item.id || `group-${index}`;
                                    const collectionId = `${stableGroupId}-${i}-${col.key}`;
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
                                                        title="Hide items in snap-ins (keeps expanded in preview/email)"
                                                        style="font-size: 0.7rem; padding: 0.1rem 0.4rem;">
                                                        👁️‍🗨️
                                                    </button>` : ""}
                                                </div>
                                                <button type="button" class="btn btn-sm btn-outline-danger remove-collection-btn" 
                                                        data-group-index="${stableGroupId}" data-collection-index="${i}">x</button>
                                            </div>
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
                         data-index="${index}" draggable="true">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="item-name">${escapeHtml(item.name)}</span>
                            <div>
                                <span class="badge badge-secondary me-2">${item.type}</span>
                                <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                            </div>
                        </div>
                        <div class="text-muted" style="font-size: 0.8rem;">A new random pick is drawn for each send; the preview shows a different pick than the send will.</div>
                    </div>
                `;
            } else {
                htmlContent += `
                    <div class="selected-item d-flex justify-content-between align-items-center p-2 mb-2 border rounded bg-light"
                         data-index="${index}" draggable="true">
                        <span class="item-name">${escapeHtml(item.name)}</span>
                        <div>
                            <span class="badge badge-secondary me-2">${item.type}</span>
                            <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" data-index="${index}">x</button>
                        </div>
                    </div>
                `;
            }
        });
        
        container.innerHTML = htmlContent;

        document.querySelectorAll('.collection-group-title').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.target.dataset.index);
                if (selectedItems[index] && selectedItems[index].type === 'collection_group') {
                    selectedItems[index].title = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });
        
        document.querySelectorAll('.remove-collection-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const stableGroupId = e.target.dataset.groupIndex;
                const groupIndex = findGroupIndexByStableId(stableGroupId);
                const collectionIndex = parseInt(e.target.dataset.collectionIndex);
                
                if (selectedItems[groupIndex] && selectedItems[groupIndex].collections) {
                    const collection = selectedItems[groupIndex].collections[collectionIndex];
                    const collectionId = `${stableGroupId}-${collectionIndex}-${collection.key}`;
                    delete window.expandedCollections[collectionId];
                    delete window.collapsedCollectionsUI[collectionId];
                    
                    selectedItems[groupIndex].collections.splice(collectionIndex, 1);
                    updateSelectedItemsDisplay();
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.expand-collection-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const stableGroupId = e.target.dataset.groupIndex;
                const groupIndex = findGroupIndexByStableId(stableGroupId);
                const collectionIndex = parseInt(e.target.dataset.collectionIndex);
                const collectionKey = e.target.dataset.collectionKey;
                const collectionType = e.target.dataset.collectionType;
                const collectionId = e.target.dataset.collectionId;
                
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
                const stableGroupId = e.target.dataset.groupIndex;
                const groupIndex = findGroupIndexByStableId(stableGroupId);
                const collectionIndex = parseInt(e.target.dataset.collectionIndex);
                const collectionId = e.target.dataset.collectionId;
                
                const expandedDiv = document.getElementById(`collection-items-${stableGroupId}-${collectionIndex}`);
                
                if (!window.collapsedCollectionsUI[collectionId]) {
                    window.collapsedCollectionsUI[collectionId] = true;
                    expandedDiv.style.display = "none";
                    e.target.textContent = "👁️";
                    e.target.title = "Show items in snap-ins";
                } else {
                    delete window.collapsedCollectionsUI[collectionId];
                    expandedDiv.style.display = "block";
                    e.target.textContent = "👁️‍🗨️";
                    e.target.title = "Hide items in snap-ins (keeps expanded in preview/email)";
                }
            });
        });

        document.querySelectorAll('.media-src-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.target.dataset.index);
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
                const index = parseInt(e.target.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].width = parseInt(e.target.value) || 400;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.media-align-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].align = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.emoji-content-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const index = parseInt(e.target.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].content = e.target.value;
                    selectedItems[index].name = `${e.target.value || 'Emoji'}`;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.emoji-size-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].size = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.emoji-align-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                if (selectedItems[index]) {
                    selectedItems[index].align = e.target.value;
                    debouncedUpdatePreview();
                }
            });
        });

        document.querySelectorAll('.media-upload-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                const input = document.getElementById('media-upload-input');
                input.dataset.targetIndex = index;
                input.click();
            });
        });

        document.querySelectorAll('.media-gif-search-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
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
        
        if (!renderedCharts.has(id)) {
            try {
                loadIBMPlexSans();

                const index = parseInt(id.split('-')[1], 10);
                const graphData = graphDataList[index];

                Highcharts.chart(id, {
                    chart: { 
                        type: 'line',
                        style: {
                            fontFamily: 'IBM Plex Sans, Segoe UI, Helvetica, Arial, sans-serif'
                        }
                    },
                    title: { text: graphCommands[index].name + ' - Last ' + currentTimeRange + ' days' },
                    exporting: { enabled: true },
                    xAxis: { categories: graphData.categories },
                    yAxis: { title: { text: hideGraphPlayCounts ? null : (statType === 'duration' ? 'Duration' : 'Plays') }, labels: { enabled: !hideGraphPlayCounts } },
                    tooltip: hideGraphPlayCounts ? { enabled: false } : {},
                    series: graphData.series
                });

                renderedCharts.add(id);
                const nowDark = document.documentElement.classList.contains('dark');
                applyChartTheme(nowDark);
            } catch (err) {
                console.warn('Failed to render graph', id, err);
            }
        }
        
        await new Promise(resolve => setTimeout(resolve, 500));
        
        const chartImage = await captureChartAsBase64(id);
        if (chartImage) {
            item.chartImage = chartImage;
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

    if (type === 'graph' && !renderedCharts.has(id)) {
        try {
            const index = parseInt(id.split('-')[1], 10);
            const graphData = graphDataList[index];

            Highcharts.chart(id, {
                chart: { type: 'line' },
                title: { text: graphCommands[index].name },
                exporting: { enabled: true },
                xAxis: { categories: graphData.categories },
                yAxis: { title: { text: hideGraphPlayCounts ? null : (statType === 'duration' ? 'Duration' : 'Plays') }, labels: { enabled: !hideGraphPlayCounts } },
                tooltip: hideGraphPlayCounts ? { enabled: false } : {},
                series: graphData.series
            });

            renderedCharts.add(id);

            const nowDark = document.documentElement.classList.contains('dark');
            applyChartTheme(nowDark);
            console.log('Auto-rendered graph:', id);
        } catch (err) {
            console.warn('Failed to auto-render graph', id, err);
        }
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

function setupDragAndDrop() {
    const items = () => Array.from(document.querySelectorAll('.selected-item'));
    const indexOfEl = (el) => allItems().indexOf(el);
    let draggedElement = null;
    
    items().forEach((item, index) => {
        item.addEventListener('dragstart', (e) => {
            draggedElement = item;
            e.dataTransfer.setData('text/plain', index);
            e.dataTransfer.effectAllowed = 'move';
            
            setTimeout(() => {
                item.classList.add('dragging');
            }, 0);
        });
        
        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            items().forEach(i => i.classList.remove('drag-over'));
            draggedElement = null;
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
        });
        
        item.addEventListener('drop', (e) => {
            e.preventDefault();
            item.classList.remove('drag-over');
            
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
        setTimeout(() => {
            setTextBlockContent(textBlockId, textContent);
            debouncedUpdatePreview();
        }, 100);
        return textBlockId;
    }
    return null;
}

function getTextBlockContent(textBlockId) {
    const textarea = document.querySelector(`[data-textblock-id="${textBlockId}"]`);
    return textarea ? textarea.value : '';
}

function setTextBlockContent(textBlockId, content) {
    const textarea = document.querySelector(`[data-textblock-id="${textBlockId}"]`);
    if (textarea) {
        textarea.value = content;
        const index = selectedItems.findIndex(item => item.id === textBlockId);
        if (index !== -1) {
            selectedItems[index].name = getTextBlockDisplayName(content);
            const nameSpan = document.querySelector(`[data-index="${index}"] .item-name`);
            if (nameSpan) {
                nameSpan.textContent = selectedItems[index].name;
            }
        }
    }
}

function getTextBlockDisplayName(content) {
    const firstLine = content.split('\n')[0].trim();
    if (firstLine.length === 0) return 'Empty text block';
    if (firstLine.substring(0, 1) === '<') return 'HTML block';
    console.log('firstChar: ' + firstLine.substring(0, 1))
    return firstLine.length > 30 ? firstLine.substring(0, 30) + '...' : firstLine;
}

function updateTextBlockName(textBlockId, index) {
    const content = getTextBlockContent(textBlockId);
    const newName = getTextBlockDisplayName(content);
    
    if (selectedItems[index]) {
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
        setTimeout(() => {
            setTextBlockContent(textBlockId, introContent);
            debouncedUpdatePreview();
        }, 100);
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
        setTimeout(() => {
            setTextBlockContent(textBlockId, outroContent);
            debouncedUpdatePreview();
        }, 100);
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
            setTimeout(() => {
                setTextBlockContent(textBlockId, titleContent);
                debouncedUpdatePreview();
            }, 100);
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
        setTimeout(() => {
            setTextBlockContent(textBlockId, headerContent);
            debouncedUpdatePreview();
        }, 100);
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

    const isAdd =
        btn.classList.contains('add-stat-btn') ||
        btn.classList.contains('add-graph-btn') ||
        btn.classList.contains('ra-add-btn') ||
        btn.classList.contains('mw-add-btn') ||
        btn.classList.contains('recs-add-btn') ||
        btn.classList.contains('droppedneedle-add-btn') ||
        btn.classList.contains('droppedneedle-server-add-btn') ||
        btn.classList.contains('yearly-wrapped-add-btn') ||
        btn.classList.contains('sonarr-coming-soon-add-btn') ||
        btn.classList.contains('radarr-coming-soon-add-btn') ||
        btn.classList.contains('ombi-requests-add-btn') ||
        btn.classList.contains('seerr-requests-add-btn');

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
