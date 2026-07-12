// Wiring for controls that previously used inline onclick attributes
// (removed for CSP compliance).

// Toggle both the body visibility and an is-collapsed class on the header so
// the chevron rotates with the state (CSS handles the rotation).
document.getElementById('cache-card-header').addEventListener('click', (e) => {
    const collapsed = document.getElementById('cache-status-badge').classList.toggle('d-none');
    e.currentTarget.classList.toggle('is-collapsed', collapsed);
});

document.getElementById('bcc-card-header').addEventListener('click', (e) => {
    const collapsed = document.getElementById('bcc-collapse').classList.toggle('d-none');
    e.currentTarget.classList.toggle('is-collapsed', collapsed);
});
