// Featured Pick snap-in: search a library and feature a specific
// title, using the same card the Random Pick renders.
let featuredPickResults = [];

function renderFeaturedPickResults() {
    const list = document.getElementById('featured-pick-results');
    if (!list) return;

    if (!featuredPickResults.length) {
        list.innerHTML = '<div class="text-muted" style="font-size: 0.85rem;">No matches.</div>';
        return;
    }

    list.innerHTML = '';
    featuredPickResults.forEach(item => {
        const row = document.createElement('div');
        row.className = 'd-flex align-items-center justify-content-between gap-2 py-1';

        const label = document.createElement('span');
        label.style.fontSize = '0.85rem';
        label.textContent = item.year ? `${item.title} (${item.year})` : item.title;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'nl-btn nl-btn--primary nl-btn--sm featured-pick-add-btn';
        btn.textContent = 'Add';
        btn.dataset.id = `featured-pick-${item.rating_key}`;
        btn.dataset.name = `Featured: ${item.title}`;
        btn.dataset.type = 'featured_pick';
        btn.dataset.ratingKey = item.rating_key;

        row.appendChild(label);
        row.appendChild(btn);
        list.appendChild(row);
    });
}

async function runFeaturedPickSearch() {
    const input = document.getElementById('featured-pick-query');
    const librarySelect = document.getElementById('featured-pick-library');
    const list = document.getElementById('featured-pick-results');
    if (!input || !list) return;

    const query = input.value.trim();
    if (!query) {
        featuredPickResults = [];
        list.innerHTML = '';
        return;
    }

    list.innerHTML = '<div class="text-muted" style="font-size: 0.85rem;">Searching...</div>';
    try {
        const params = new URLSearchParams({ q: query });
        const sectionId = librarySelect?.value || '';
        if (sectionId) params.set('section_id', sectionId);
        const resp = await fetch(`/featured_pick_search?${params.toString()}`, { credentials: 'same-origin' });
        const data = await resp.json();
        featuredPickResults = (data.status === 'success' && Array.isArray(data.results)) ? data.results : [];
        renderFeaturedPickResults();
    } catch (e) {
        console.error('Featured pick search failed:', e);
        list.innerHTML = '<div class="text-muted" style="font-size: 0.85rem;">Search failed.</div>';
    }
}

function initFeaturedPickCard() {
    const card = document.getElementById('featured-pick-card');
    const librarySelect = document.getElementById('featured-pick-library');
    const input = document.getElementById('featured-pick-query');
    const searchBtn = document.getElementById('featured-pick-search-btn');
    if (!card || !input || !searchBtn) return;

    // Shares the Random Pick library list: both need "libraries Plex exposes",
    // and it is already fetched there.
    if (librarySelect && Array.isArray(randomPickLibraries)) {
        randomPickLibraries.forEach(lib => {
            const opt = document.createElement('option');
            opt.value = lib.section_id;
            opt.textContent = lib.title;
            librarySelect.appendChild(opt);
        });
        if (randomPickLibraries.length) card.style.display = '';
    }

    searchBtn.addEventListener('click', runFeaturedPickSearch);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            runFeaturedPickSearch();
        }
    });
}

// randomPickLibraries is filled by an async fetch in 32-random-pick.js; poll
// briefly rather than racing it, and give up quietly when Plex is absent.
document.addEventListener('DOMContentLoaded', () => {
    let tries = 0;
    const tick = setInterval(() => {
        tries += 1;
        if (typeof randomPickLibraries !== 'undefined' && randomPickLibraries.length) {
            clearInterval(tick);
            initFeaturedPickCard();
        } else if (tries > 20) {
            clearInterval(tick);
        }
    }, 250);
});
