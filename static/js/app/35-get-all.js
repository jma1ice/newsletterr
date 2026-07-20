// Get All (NEWS-36): run every configured pull in sequence, reusing each
// pull's own runner (window.pullRunners.*) so the spinner and its real progress
// bar walk through the chain step by step. No backend route of its own; it just
// awaits the existing per-pull fetches back to back.
//
// Order matters: stats/users first because recommendations and DroppedNeedle
// need the recipient list it loads, then the standalone services. A failure in
// one pull never aborts the chain; a single confirm up front replaces the
// per-pull two-click guards, and the recs pull's own Cancel button keeps
// working mid-chain.
(function () {
    const btn = document.getElementById('getAllBtn');
    if (!btn) return;

    function hasRecipients() {
        // recommendations/DroppedNeedle read the BCC chip list, which Get Stats
        // populates; fall back to userDict so a manually entered list counts too
        const chips = document.querySelectorAll('#bcc_chips .nl-chip');
        if (chips.length) return true;
        return !!(typeof userDict !== 'undefined' && userDict && Object.keys(userDict).length);
    }

    btn.addEventListener('click', async () => {
        const flags = (window.APP && window.APP.serviceFlags) || {};
        const steps = [];
        if (flags.tautulli) steps.push({ key: 'stats', label: 'Stats & Users' });
        if (flags.conjurr) steps.push({ key: 'recommendations', label: 'Recommendations', needsUsers: true });
        if (flags.droppedneedle) steps.push({ key: 'droppedneedle', label: 'DroppedNeedle Stats', needsUsers: true });
        if (flags.calendar) steps.push({ key: 'coming_soon', label: 'Coming Soon Calendar' });
        if (flags.ombi) steps.push({ key: 'ombi', label: 'Ombi Requests' });
        if (flags.seerr) steps.push({ key: 'seerr', label: 'Seerr Requests' });
        if (!steps.length) return;

        const estimate = flags.conjurr
            ? '\n\nRecommendations run last-but-one and take about 20-25 seconds per user.'
            : '';
        if (!window.confirm(`Run all ${steps.length} configured pulls in sequence?${estimate}`)) return;

        const label = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Getting all...';

        const succeeded = [], failed = [], skipped = [];
        try {
            for (const step of steps) {
                const runner = window.pullRunners && window.pullRunners[step.key];
                if (typeof runner !== 'function') { skipped.push(`${step.label} (unavailable)`); continue; }
                if (step.needsUsers && !hasRecipients()) { skipped.push(`${step.label} (no recipients yet)`); continue; }
                try {
                    const res = await runner({ chained: true });
                    if (res && res.ok) succeeded.push(step.label);
                    else failed.push(step.label + (res && res.error ? `: ${res.error}` : ''));
                } catch (err) {
                    failed.push(`${step.label}: ${String((err && err.message) || err)}`);
                }
            }
        } finally {
            btn.disabled = false;
            btn.textContent = label;
        }

        const summary = [];
        if (succeeded.length) summary.push('Completed: ' + succeeded.join(', '));
        if (skipped.length) summary.push('Skipped: ' + skipped.join(', '));
        if (failed.length) summary.push('Failed: ' + failed.join(', '));
        alert(summary.join('\n') || 'Nothing to pull.');
    });
})();
