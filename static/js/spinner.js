/* Shared loading spinner: showSpinner(text, opName) / hideSpinner(). Used by
   the app shell (base.html) and the standalone setup page (setup.html).

   - Each show picks a random loader gif. When a pride theme is active on <html>
     it picks from the pride set, otherwise the default set.
   - The caller's text is pinned on #loading-text (so must-see values like a Plex
     pairing code never scroll away). A second line, #loading-tip, rotates a mix
     of tips, status flavor, contributor shout-outs, and quips every 5 seconds.
   - When opName is passed, /pull_progress?op=<name> is polled while visible and
     #loading-progress fills as the backend reports steps; the reported label
     replaces the pinned text. Without opName (or on pages without the bar, like
     setup.html) behavior is unchanged. */
(function () {
    const NORMAL_GIFS = ['Asset_45752', 'Asset_75200', 'Asset_79466'];
    const PRIDE_GIFS = ['Asset_10465', 'Asset_24165', 'Asset_37112', 'Asset_87388', 'Asset_90828'];

    // Contributor handles are kept in sync with the About page.
    const TIPS = [
        // tips and tricks
        'Tip: collapse the sidebar with the chevron for more room.',
        'Tip: toggle light and dark mode from the bottom of the sidebar.',
        'Tip: pick a pride theme under Settings then Appearance.',
        'Tip: flip on Custom HTML Mode to hand-craft your email.',
        'Tip: send yourself a test email before the real send.',
        'Tip: pop out the preview pane to see changes as you build.',
        'Tip: adjust the time range to change which items get pulled.',
        // status flavor (what it might be up to)
        'Crunching the numbers...',
        'Warming up the mail room...',
        'Wrangling your media stats...',
        'Polishing the pixels...',
        'Lining up the newsletters...',
        'Tightening a few bolts...',
        // contributor shout-outs, colored to match the About page tiers
        // (gold = contrib-group--gold, green = contrib-group--green)
        { text: 'Thanks to @baggins for helping keep newsletterr alive!', tier: 'gold' },
        { text: 'Shoutout to @dreondre for contributing on GitHub!', tier: 'gold' },
        { text: 'Thanks to @taehatypes for the support!', tier: 'green' },
        { text: 'Shoutout to @quinneydavid for contributing on GitHub!', tier: 'green' },
        { text: 'Thanks to @bferd for the support!', tier: 'green' },
        // quips
        'Good things come to those who wait...',
        'Herding a few cats...',
        'Reticulating splines...',
        'Almost there, promise.',
        'Loading, but make it fashion.'
    ];

    let tipTimer = null;
    let lastTip = -1;
    let progressTimer = null;

    function stopProgressPolling() {
        clearInterval(progressTimer);
        progressTimer = null;
        const bar = document.getElementById('loading-progress');
        if (bar) bar.style.display = 'none';
        const fill = document.getElementById('loading-progress-fill');
        if (fill) fill.style.width = '0%';
    }

    function startProgressPolling(opName) {
        const bar = document.getElementById('loading-progress');
        const fill = document.getElementById('loading-progress-fill');
        if (!bar || !fill) return;
        progressTimer = setInterval(async () => {
            let p;
            try {
                const resp = await fetch(`/pull_progress?op=${encodeURIComponent(opName)}`);
                if (!resp.ok) return;
                p = await resp.json();
            } catch (_) {
                return;
            }
            if (!p || !p.total) return;
            bar.style.display = 'block';
            fill.style.width = `${Math.min(100, Math.round((p.step / p.total) * 100))}%`;
            const textEl = document.getElementById('loading-text');
            if (textEl && p.label) textEl.textContent = p.label;
        }, 500);
    }

    function pickIndex(len, exclude) {
        if (len <= 1) return 0;
        let i;
        do { i = Math.floor(Math.random() * len); } while (i === exclude);
        return i;
    }

    function randomGif() {
        const set = document.documentElement.classList.contains('pride') ? PRIDE_GIFS : NORMAL_GIFS;
        return '/static/img/' + set[Math.floor(Math.random() * set.length)] + '.gif';
    }

    function rotateTip() {
        const el = document.getElementById('loading-tip');
        if (!el) return;
        lastTip = pickIndex(TIPS.length, lastTip);
        const tip = TIPS[lastTip];
        const tier = typeof tip === 'string' ? null : tip.tier;
        el.textContent = typeof tip === 'string' ? tip : tip.text;
        el.classList.toggle('spinner-tip--gold', tier === 'gold');
        el.classList.toggle('spinner-tip--green', tier === 'green');
    }

    window.showSpinner = function (passedText, opName) {
        const spinner = document.getElementById('spinner');
        if (!spinner) return;
        // Reveal the overlay before swapping the mascot: Safari sometimes never
        // starts animating a gif whose src changed while display was none.
        spinner.style.display = 'flex';
        const oldImg = spinner.querySelector('img');
        if (oldImg) {
            // A fresh <img> node (rather than mutating .src) plus a cache-busting
            // query reliably kicks Safari into playing the gif from frame 0.
            const fresh = document.createElement('img');
            fresh.alt = oldImg.alt || 'Loading...';
            if (oldImg.className) fresh.className = oldImg.className;
            fresh.src = randomGif() + '?t=' + Date.now();
            oldImg.replaceWith(fresh);
        }
        const textEl = document.getElementById('loading-text');
        if (textEl) textEl.textContent = passedText || '';
        rotateTip();
        clearInterval(tipTimer);
        tipTimer = setInterval(rotateTip, 5000);
        stopProgressPolling();
        if (opName) startProgressPolling(opName);
    };

    window.hideSpinner = function () {
        const spinner = document.getElementById('spinner');
        if (spinner) spinner.style.display = 'none';
        clearInterval(tipTimer);
        tipTimer = null;
        stopProgressPolling();
        const tipEl = document.getElementById('loading-tip');
        if (tipEl) tipEl.textContent = '';
    };
})();
