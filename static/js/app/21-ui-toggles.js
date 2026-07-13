// Wiring for controls that previously used inline onclick attributes
// (removed for CSP compliance).

// Toggle both the body visibility and an is-collapsed class on the header so
// the chevron rotates with the state (CSS handles the rotation).
const cacheCardHeader = document.getElementById('cache-card-header');
if (cacheCardHeader) {
    cacheCardHeader.addEventListener('click', (e) => {
        const collapsed = document.getElementById('cache-status-badge').classList.toggle('d-none');
        e.currentTarget.classList.toggle('is-collapsed', collapsed);
    });
}
