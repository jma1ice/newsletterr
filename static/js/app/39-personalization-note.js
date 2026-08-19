// a personalization token makes the body differ per recipient, so the
// send stops being one BCC message and becomes one message each. That is worth
// knowing while the token is being written, not after a slow send, so this
// watches the places a token can be typed and shows the note when one appears.
(function () {
    const note = document.getElementById('personalization-note');
    if (!note) return;

    // must match app/emails/personalization.py TOKEN_RE
    const TOKEN_RE = /\{\{\s*(name|email|first_name)\s*\}\}/i;

    function anyTokenPresent() {
        const custom = document.getElementById('custom-html-editor');
        if (custom && custom.value && TOKEN_RE.test(custom.value)) return true;

        // text blocks: the textarea/rich editor inside each selected item, plus
        // the standalone message body
        const fields = document.querySelectorAll(
            '#selected-items-list textarea, #selected-items-list [contenteditable="true"], #email_text'
        );
        for (const el of fields) {
            const text = 'value' in el && el.value !== undefined ? el.value : el.innerHTML;
            if (text && TOKEN_RE.test(text)) return true;
        }
        return false;
    }

    function sync() {
        note.classList.toggle('d-none', !anyTokenPresent());
    }

    // input covers typing; the observer covers snap-ins being added, removed or
    // reordered, and a template being loaded
    document.addEventListener('input', sync);
    document.addEventListener('change', sync);
    const list = document.getElementById('selected-items-list');
    if (list && window.MutationObserver) {
        new MutationObserver(sync).observe(list, { childList: true, subtree: true });
    }
    sync();
})();
