// Quick time-range buttons. The whole pull rail is absent in standalone mode
// so every binding here is guarded: these are classic scripts sharing globals,
// and a throw at the top level of one file stops the rest of that file from running.
[
    ['time_range_week', 7],
    ['time_range_month', 30],
    ['time_range_quarter', 90],
    ['time_range_two_q', 180],
    ['time_range_three_q', 270],
    ['time_range_year', 365],
].forEach(([id, days]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener('click', () => {
        const input = document.getElementById('days_to_pull');
        const form = document.getElementById('stats_form');
        if (!input || !form) return;
        input.value = days;
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
});
