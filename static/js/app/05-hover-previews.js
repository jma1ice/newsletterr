function showRecsPreviewFor(userKey) {
    const preview = document.getElementById('recs-preview');
    if (!preview) return;
    const header = preview.querySelector('.card-header');
    if (header) header.textContent = `Recommendations - ${userDict[userKey] || userKey}`;
    const body = preview.querySelector('.card-body');
    body.innerHTML = '';
    body.appendChild(buildRecsBlockForUser(userKey, { headingTag: 'h4' }, { bgColorway: 'view' }));
    preview.style.display = 'block';
}

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('recs-view-btn')) {
        const viewBtn = e.target.closest('.recs-view-btn');
        if (viewBtn) {
            const userKey = viewBtn.dataset.userKey;
            if (userKey) showRecsPreviewFor(userKey);
            return;
        }
    }
});
