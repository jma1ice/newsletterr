// Wiring for controls that previously used inline onclick attributes
// (removed for CSP compliance).

document.getElementById('cache-card-header').addEventListener('click', () => {
    document.getElementById('cache-status-badge').classList.toggle('d-none');
});

document.getElementById('bcc-card-header').addEventListener('click', () => {
    document.getElementById('bcc-collapse').classList.toggle('d-none');
});
