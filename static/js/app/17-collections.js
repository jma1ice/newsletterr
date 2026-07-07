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

function buildCollectionPreviewHTML(collection) {
    const typeIcon = collection.subtype === 'movie' ? '📽️' : collection.subtype === 'movie' ? '📺' : '🎧';
    
    return `
        <div class="collection-preview card my-3">
            <div class="card-header d-flex align-items-center">
                <span class="me-2" style="font-size: 1.2em;">${typeIcon}</span>
                <h5 class="mb-0">${collection.title}</h5>
                <span class="badge bg-secondary ms-auto">${collection.childCount} items</span>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-3">
                        ${collection.thumb ? 
                            `<img src="${collection.thumb}" class="img-fluid rounded" alt="${collection.title}" style="max-height: 200px; object-fit: cover;">` :
                            `<div class="placeholder-image d-flex align-items-center justify-content-center bg-light rounded" style="height: 200px;">
                                <span class="text-muted">${typeIcon} No Poster</span>
                            </div>`
                        }
                    </div>
                    <div class="col-md-9">
                        <p><strong>Library:</strong> ${collection.sectionTitle}</p>
                        <p><strong>Type:</strong> ${collection.subtype.charAt(0).toUpperCase() + collection.subtype.slice(1)} Collection</p>
                        ${collection.summary ? `<p><strong>Description:</strong> ${collection.summary}</p>` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;
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

document.getElementById('add-collection-group-btn').addEventListener('click', function() {
    collectionGroupCounter++;
    const groupId = `collection-group-${collectionGroupCounter}`;
    
    const newGroup = {
        id: groupId,
        name: 'Collection Group',
        type: 'collection_group',
        title: 'New Collection Group',
        collections: []
    };
    
    selectedItems.push(newGroup);
    updateSelectedItemsDisplay();
});

function addCollectionItem(collection) {
    let targetGroup = null;
    for (let i = selectedItems.length - 1; i >= 0; i--) {
        if (selectedItems[i].type === 'collection_group') {
            targetGroup = selectedItems[i];
            break;
        }
    }
    
    if (!targetGroup) {
        collectionGroupCounter++;
        targetGroup = {
            id: `collection-group-${collectionGroupCounter}`,
            name: 'Collection Group',
            type: 'collection_group',
            title: 'New Collection Group',
            collections: []
        };
        selectedItems.push(targetGroup);
    }
    
    const exists = targetGroup.collections.some(c => c.key === collection.key);
    if (exists) {
        console.log('Collection already in this group:', collection.title);
        return;
    }
    
    targetGroup.collections.push(collection);
    updateSelectedItemsDisplay();
    
    document.getElementById('movie-collections-dropdown').value = '';
    document.getElementById('show-collections-dropdown').value = '';
    document.getElementById('audio-collections-dropdown').value = '';
    document.getElementById('add-movie-collection-btn').disabled = true;
    document.getElementById('add-show-collection-btn').disabled = true;
    document.getElementById('add-audio-collection-btn').disabled = true;
    
    console.log('Added collection to group:', collection.title);
}

document.addEventListener('DOMContentLoaded', loadCollections);
