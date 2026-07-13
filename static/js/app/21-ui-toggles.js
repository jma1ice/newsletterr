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

// Recipients toggle: chevron collapses the nested list selector + BCC chips so
// the message bar stays compact. Default-collapsed state is set in the markup.
const bccCardHeader = document.getElementById('bcc-card-header');
if (bccCardHeader) {
    bccCardHeader.addEventListener('click', (e) => {
        const collapsed = document.getElementById('bcc-collapse').classList.toggle('d-none');
        e.currentTarget.classList.toggle('is-collapsed', collapsed);
        e.currentTarget.setAttribute('aria-expanded', String(!collapsed));
    });
}
