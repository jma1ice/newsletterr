(function initGifPicker() {
    let currentTargetIndex = null;
    let currentPage = 1;
    let currentQuery = '';
    let isLoading = false;

    function openGifPicker(index) {
        currentTargetIndex = index;
        currentPage = 1;
        currentQuery = '';
        document.getElementById('gif-search-input').value = '';
        document.getElementById('gif-results-grid').innerHTML = `
            <div id="gif-results-empty" style="grid-column: 1/-1; text-align: center; padding: 40px; color: #888;">
                Search for GIFs above
            </div>`;
        document.getElementById('gif-prev-btn').disabled = true;
        document.getElementById('gif-next-btn').disabled = true;
        document.getElementById('gif-page-label').textContent = 'Page 1';
        document.getElementById('gif-picker-modal').style.display = 'block';
        document.getElementById('gif-search-input').focus();
    }

    function closeGifPicker() {
        document.getElementById('gif-picker-modal').style.display = 'none';
        currentTargetIndex = null;
    }

    async function searchGifs(query, page = 1) {
        if (!query.trim() || isLoading) return;
        isLoading = true;

        const grid = document.getElementById('gif-results-grid');
        grid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #888;">
                <div class="spinner-border spinner-border-sm" role="status"></div>
                <span class="ms-2">Searching...</span>
            </div>`;
        document.getElementById('gif-prev-btn').disabled = true;
        document.getElementById('gif-next-btn').disabled = true;

        try {
            const resp = await fetch(
                `/api/gif/search?q=${encodeURIComponent(query)}&page=${page}&per_page=12`,
                { credentials: 'same-origin' }
            );
            const data = await resp.json();

            if (data.error) {
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #c00;">${data.error}</div>`;
                return;
            }

            const results = data.results || [];
            if (results.length === 0) {
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #888;">No results for "${query}"</div>`;
                return;
            }

            grid.innerHTML = results.map(gif => `
                <div class="gif-result-item" data-url="${gif.url}" data-title="${gif.title || ''}"
                    style="cursor: pointer; border-radius: 6px; overflow: hidden; aspect-ratio: 1; background: #111; position: relative;">
                    <img src="${gif.preview_url || gif.url}"
                        alt="${gif.title || ''}"
                        loading="lazy"
                        style="width: 100%; height: 100%; object-fit: cover; display: block; transition: opacity 0.2s;"
                        onmouseover="this.style.opacity='0.8'"
                        onmouseout="this.style.opacity='1'">
                </div>
            `).join('');

            document.getElementById('gif-page-label').textContent = `Page ${page}`;
            document.getElementById('gif-prev-btn').disabled = page <= 1;
            document.getElementById('gif-next-btn').disabled = results.length < 12;

            document.querySelectorAll('.gif-result-item').forEach(el => {
                el.addEventListener('click', () => {
                    const url = el.dataset.url;
                    if (currentTargetIndex !== null && selectedItems[currentTargetIndex]) {
                        selectedItems[currentTargetIndex].src = url;
                        selectedItems[currentTargetIndex].type = 'gif';
                        selectedItems[currentTargetIndex].name = 'GIF';
                    } else {
                        mediaBlockCounter++;
                        const id = `gif-block-${mediaBlockCounter}`;
                        selectedItems.push({ id, name: 'GIF', type: 'gif', src: url, width: 400, align: 'center' });
                    }
                    updateSelectedItemsDisplay();
                    debouncedUpdatePreview();
                    closeGifPicker();
                });
            });

        } catch (err) {
            console.error('GIF search error:', err);
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #c00;">Search failed. Please try again.</div>`;
        } finally {
            isLoading = false;
        }
    }

    document.getElementById('gif-search-btn').addEventListener('click', () => {
        currentQuery = document.getElementById('gif-search-input').value;
        currentPage = 1;
        searchGifs(currentQuery, currentPage);
    });

    document.getElementById('gif-search-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            currentQuery = e.target.value;
            currentPage = 1;
            searchGifs(currentQuery, currentPage);
        }
    });

    document.getElementById('gif-prev-btn').addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            searchGifs(currentQuery, currentPage);
        }
    });

    document.getElementById('gif-next-btn').addEventListener('click', () => {
        currentPage++;
        searchGifs(currentQuery, currentPage);
    });

    document.getElementById('gif-picker-close').addEventListener('click', closeGifPicker);
    document.getElementById('gif-picker-modal').addEventListener('click', (e) => {
        if (e.target === document.getElementById('gif-picker-modal')) closeGifPicker();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && document.getElementById('gif-picker-modal').style.display === 'block') {
            closeGifPicker();
        }
    });

    window.openGifPicker = openGifPicker;
})();
