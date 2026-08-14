let movieCollections = [];
let showCollections = [];

async function loadCollections() {
    try {
        document.getElementById('movie-collections-loading').classList.remove('d-none');
        const movieResponse = await fetch('/fetch_collections/movie');
        const movieData = await movieResponse.json();
        
        if (movieData.status === 'success') {
            movieCollections = movieData.collections;
            populateCollectionsDropdown('movie-collections-dropdown', movieCollections);
        } else {
            console.error('Error loading movie collections:', movieData.message);
        }
        document.getElementById('movie-collections-loading').classList.add('d-none');

        document.getElementById('show-collections-loading').classList.remove('d-none');
        const showResponse = await fetch('/fetch_collections/show');
        const showData = await showResponse.json();
        
        if (showData.status === 'success') {
            showCollections = showData.collections;
            populateCollectionsDropdown('show-collections-dropdown', showCollections);
        } else {
            console.error('Error loading show collections:', showData.message);
        }
        document.getElementById('show-collections-loading').classList.add('d-none');

        document.getElementById('audio-collections-loading').classList.remove('d-none');
        const audioResponse = await fetch('/fetch_collections/artist');
        const audioData = await audioResponse.json();
        
        if (audioData.status === 'success') {
            audioCollections = audioData.collections;
            populateCollectionsDropdown('audio-collections-dropdown', audioCollections);
        } else {
            console.error('Error loading audio collections:', audioData.message);
        }
        document.getElementById('audio-collections-loading').classList.add('d-none');

    } catch (error) {
        console.error('Error loading collections:', error);
        document.getElementById('movie-collections-loading').classList.add('d-none');
        document.getElementById('show-collections-loading').classList.add('d-none');
        document.getElementById('audio-collections-loading').classList.add('d-none');
    }
}

function populateCollectionsDropdown(dropdownId, collections) {
    const dropdown = document.getElementById(dropdownId);
    
    while (dropdown.children.length > 1) {
        dropdown.removeChild(dropdown.lastChild);
    }

    collections.forEach(collection => {
        const option = document.createElement('option');
        option.value = collection.key;
        option.textContent = `${collection.title} (${collection.childCount} items)`;
        option.dataset.collection = JSON.stringify(collection);
        dropdown.appendChild(option);
    });
}

document.getElementById('movie-collections-dropdown').addEventListener('change', function() {
    const button = document.getElementById('add-movie-collection-btn');
    
    if (this.value) {
        button.disabled = false;
    } else {
        button.disabled = true;
    }
    
    document.getElementById('show-collections-dropdown').value = '';
    document.getElementById('add-show-collection-btn').disabled = true;
    document.getElementById('audio-collections-dropdown').value = '';
    document.getElementById('add-audio-collection-btn').disabled = true;
});

document.getElementById('show-collections-dropdown').addEventListener('change', function() {
    const button = document.getElementById('add-show-collection-btn');
    
    if (this.value) {
        button.disabled = false;
    } else {
        button.disabled = true;
    }
    
    document.getElementById('movie-collections-dropdown').value = '';
    document.getElementById('add-movie-collection-btn').disabled = true;
    document.getElementById('audio-collections-dropdown').value = '';
    document.getElementById('add-audio-collection-btn').disabled = true;
});

document.getElementById('audio-collections-dropdown').addEventListener('change', function() {
    const button = document.getElementById('add-audio-collection-btn');
    
    if (this.value) {
        button.disabled = false;
    } else {
        button.disabled = true;
    }
    
    document.getElementById('movie-collections-dropdown').value = '';
    document.getElementById('add-movie-collection-btn').disabled = true;
    document.getElementById('show-collections-dropdown').value = '';
    document.getElementById('add-show-collection-btn').disabled = true;
});

document.getElementById('add-movie-collection-btn').addEventListener('click', function() {
    const dropdown = document.getElementById('movie-collections-dropdown');
    if (dropdown.value) {
        const collection = JSON.parse(dropdown.selectedOptions[0].dataset.collection);
        addCollectionItem(collection);
    }
});

document.getElementById('add-show-collection-btn').addEventListener('click', function() {
    const dropdown = document.getElementById('show-collections-dropdown');
    if (dropdown.value) {
        const collection = JSON.parse(dropdown.selectedOptions[0].dataset.collection);
        addCollectionItem(collection);
    }
});

document.getElementById('add-audio-collection-btn').addEventListener('click', function() {
    const dropdown = document.getElementById('audio-collections-dropdown');
    if (dropdown.value) {
        const collection = JSON.parse(dropdown.selectedOptions[0].dataset.collection);
        addCollectionItem(collection);
    }
});

let collectionGroupCounter = 0;

function collectionGroups() {
    return selectedItems.filter(item => item && item.type === 'collection_group');
}

function newCollectionGroup() {
    collectionGroupCounter++;
    return {
        id: `collection-group-${collectionGroupCounter}`,
        name: 'Collection Group',
        type: 'collection_group',
        title: 'New Collection Group',
        collections: []
    };
}

document.getElementById('add-collection-group-btn').addEventListener('click', function() {
    const group = newCollectionGroup();
    selectedItems.push(group);
    updateSelectedItemsDisplay();
    // A brand new group is almost certainly what the next Add is meant for.
    const target = document.getElementById('collection-target-group');
    if (target) target.value = group.id;
});

function refreshCollectionTargetOptions() {
    const row = document.getElementById('collection-target-row');
    const select = document.getElementById('collection-target-group');
    if (!row || !select) return;

    const groups = collectionGroups();
    const previous = select.value;

    select.innerHTML = '';
    groups.forEach(group => {
        const option = document.createElement('option');
        option.value = group.id;
        option.textContent = group.title || 'Unnamed Collection Group';
        select.appendChild(option);
    });

    // Hold the previous choice across re-renders; otherwise fall back to the
    // last group, which is where Add always used to land.
    if (groups.some(g => g.id === previous)) {
        select.value = previous;
    } else if (groups.length) {
        select.value = groups[groups.length - 1].id;
    }

    // Toggle both: `d-flex` and `d-none` cannot coexist on one element,
    // since utilities.css declares d-flex last and both are !important.
    const hide = groups.length < 2;
    row.classList.toggle('d-none', hide);
    row.classList.toggle('d-flex', !hide);
}

function targetCollectionGroup() {
    const select = document.getElementById('collection-target-group');
    const chosen = select && selectedItems.find(
        item => item && item.type === 'collection_group' && item.id === select.value
    );
    if (chosen) return chosen;

    const groups = collectionGroups();
    if (groups.length) return groups[groups.length - 1];

    const created = newCollectionGroup();
    selectedItems.push(created);
    return created;
}

function addCollectionItem(collection) {
    const targetGroup = targetCollectionGroup();

    const exists = targetGroup.collections.some(c => c.key === collection.key);
    if (exists) {
        console.log('Collection already in this group:', collection.title);
        return;
    }

    targetGroup.collections.push(collection);
    updateSelectedItemsDisplay();
    if (typeof debouncedUpdatePreview === 'function') debouncedUpdatePreview();

    document.getElementById('movie-collections-dropdown').value = '';
    document.getElementById('show-collections-dropdown').value = '';
    document.getElementById('audio-collections-dropdown').value = '';
    document.getElementById('add-movie-collection-btn').disabled = true;
    document.getElementById('add-show-collection-btn').disabled = true;
    document.getElementById('add-audio-collection-btn').disabled = true;

    console.log('Added collection to group:', collection.title);
}

function moveCollectionToGroup(fromGroupId, collectionIndex, toGroupId) {
    if (fromGroupId === toGroupId) return true;

    const from = selectedItems.find(i => i && i.type === 'collection_group' && i.id === fromGroupId);
    const to = selectedItems.find(i => i && i.type === 'collection_group' && i.id === toGroupId);
    if (!from || !to || !from.collections[collectionIndex]) return false;

    const collection = from.collections[collectionIndex];
    if (to.collections.some(c => c.key === collection.key)) {
        // The destination already has it; leave both sides untouched.
        return false;
    }

    const oldKey = collectionExpansionKey(fromGroupId, collection.key);
    const newKey = collectionExpansionKey(toGroupId, collection.key);
    if (window.expandedCollections[oldKey]) {
        window.expandedCollections[newKey] = window.expandedCollections[oldKey];
        delete window.expandedCollections[oldKey];
    }
    if (window.collapsedCollectionsUI[oldKey]) {
        window.collapsedCollectionsUI[newKey] = window.collapsedCollectionsUI[oldKey];
        delete window.collapsedCollectionsUI[oldKey];
    }

    from.collections.splice(collectionIndex, 1);
    to.collections.push(collection);

    updateSelectedItemsDisplay();
    if (typeof debouncedUpdatePreview === 'function') debouncedUpdatePreview();
    return true;
}

document.addEventListener('DOMContentLoaded', loadCollections);
