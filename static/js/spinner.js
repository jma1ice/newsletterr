/* Shared loading spinner: showSpinner(text) / hideSpinner(). Used by the app
   shell (base.html) and the standalone setup page (setup.html).

   - Each show picks a random loader gif. When a pride theme is active on <html>
     it picks from the pride set, otherwise the default set.
   - The caller's text is pinned on #loading-text (so must-see values like a Plex
     pairing code never scroll away). A second line, #loading-tip, rotates a mix
     of tips, status flavor, contributor shout-outs, and quips every 5 seconds. */
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
        // contributor shout-outs
        'Thanks to @baggins for helping keep newsletterr alive!',
        'Shoutout to @dreondre for contributing on GitHub!',
        'Thanks to @taehatypes for the support!',
        'Shoutout to @quinneydavid for contributing on GitHub!',
        'Thanks to @bferd for the support!',
        // quips
        'Good things come to those who wait...',
        'Herding a few cats...',
        'Reticulating splines...',
        'Almost there, promise.',
        'Loading, but make it fashion.'
    ];

    let tipTimer = null;
    let lastTip = -1;

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
        el.textContent = TIPS[lastTip];
    }

    window.showSpinner = function (passedText) {
        const spinner = document.getElementById('spinner');
        if (!spinner) return;
        const img = spinner.querySelector('img');
        if (img) img.src = randomGif();
        const textEl = document.getElementById('loading-text');
        if (textEl) textEl.textContent = passedText || '';
        spinner.style.display = 'flex';
        rotateTip();
        clearInterval(tipTimer);
        tipTimer = setInterval(rotateTip, 5000);
    };

    window.hideSpinner = function () {
        const spinner = document.getElementById('spinner');
        if (spinner) spinner.style.display = 'none';
        clearInterval(tipTimer);
        tipTimer = null;
        const tipEl = document.getElementById('loading-tip');
        if (tipEl) tipEl.textContent = '';
    };
})();
