// Random Pick snap-in (NEWS-17): library + optional genre dropdowns backed by
// /random_pick_options. The card stays hidden until Plex returns at least one
// eligible library. The pick itself is drawn server-side at render time, so
// preview and each send feature a fresh item.
let randomPickLibraries = [];

function populateRandomPickGenres(sectionId) {
    const genreSelect = document.getElementById('random-pick-genre');
    if (!genreSelect) return;
    genreSelect.innerHTML = '<option value="">Any genre</option>';
    const lib = randomPickLibraries.find(l => l.section_id === sectionId);
    const genres = lib?.genres || [];
    genres.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.id;
        opt.textContent = g.title;
        genreSelect.appendChild(opt);
    });
    genreSelect.disabled = genres.length === 0;
}

async function initRandomPickCard() {
    const card = document.getElementById('random-pick-card');
    const librarySelect = document.getElementById('random-pick-library');
    const genreSelect = document.getElementById('random-pick-genre');
    const addBtn = document.getElementById('random-pick-add-btn');
    if (!card || !librarySelect || !genreSelect || !addBtn) return;

    try {
        const resp = await fetch('/random_pick_options');
        const data = await resp.json();
        if (data.status !== 'success' || !Array.isArray(data.libraries) || data.libraries.length === 0) return;
        randomPickLibraries = data.libraries;
    } catch (e) {
        console.log('Random pick options unavailable:', e);
        return;
    }

    randomPickLibraries.forEach(lib => {
        const opt = document.createElement('option');
        opt.value = lib.section_id;
        opt.textContent = lib.title;
        librarySelect.appendChild(opt);
    });
    card.style.display = '';

    librarySelect.addEventListener('change', () => {
        populateRandomPickGenres(librarySelect.value);
        addBtn.disabled = !librarySelect.value;
    });

    addBtn.addEventListener('click', async () => {
        const sectionId = librarySelect.value;
        if (!sectionId) return;
        const lib = randomPickLibraries.find(l => l.section_id === sectionId);
        const library = lib ? lib.title : sectionId;
        const genre = genreSelect.value || '';
        const genreLabel = genre ? (genreSelect.options[genreSelect.selectedIndex]?.textContent || '') : '';

        const id = `random-pick-${sectionId}${genre ? '-' + genre : ''}`;
        const name = `Random Pick: ${library}${genreLabel ? ' (' + genreLabel + ')' : ''}`;
        const extra = { sectionId, library };
        if (genre) {
            extra.genre = genre;
            extra.genreLabel = genreLabel;
        }

        if (await addItemWithChartCapture(id, name, 'random_pick', extra)) {
            const prevText = addBtn.textContent;
            addBtn.textContent = 'Added';
            addBtn.classList.remove('nl-btn--primary');
            addBtn.classList.add('nl-btn--success');
            setTimeout(() => {
                addBtn.textContent = prevText;
                addBtn.classList.remove('nl-btn--success');
                addBtn.classList.add('nl-btn--primary');
            }, 1200);
        }
    });
}

document.addEventListener('DOMContentLoaded', initRandomPickCard);
