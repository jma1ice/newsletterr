(function () {
    const box = document.getElementById('bcc_chips');
    const input = document.getElementById('email_chip_input');
    const ta = document.getElementById('to_emails');

    if (!box || !input || !ta) return;

    function normalize(token) {
        const m = String(token).match(/<([^>]+)>/);
        return (m ? m[1] : token).trim().toLowerCase();
    }
    function isEmail(s) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
    }

    function syncHiddenFromDOM() {
        const list = Array.from(box.querySelectorAll('.nl-chip'))
            .map(ch => ch.dataset.email)
            .filter(Boolean);
        ta.value = list.join(', ');
        input.placeholder = 'Add BCC emails';
        const countEl = document.getElementById('bcc-count');
        if (countEl) countEl.textContent = `(${list.length})`;
    }

    function makeChip(email) {
        const chip = document.createElement('span');
        chip.className = 'nl-chip';
        chip.dataset.email = email;
        chip.innerHTML = `
            <span>${escapeHtml(email)}</span>
            <button type="button" class="remove" aria-label="Remove ${escapeHtml(email)}">x</button>
        `;
        return chip;
    }

    function addEmail(email) {
        if (!email || !isEmail(email)) {
            return;
        };
        const sel = `.nl-chip[data-email="${CSS.escape(email)}"]`;
        if (box.querySelector(sel)) {
            return;
        };
        box.insertBefore(makeChip(email), input);
        syncHiddenFromDOM();
    }

    function addTokens(str) {
        String(str).split(/[,\n;\s]+/).filter(Boolean).forEach(t => {
            addEmail(normalize(t));
        });
    }
    window.chipsAddTokens = (str) => {
        chipsObserver.disconnect();
        String(str).split(/[,\n;\s]+/).filter(Boolean).forEach(t => {
            addEmail(normalize(t));
        });
        chipsObserver.observe(box, { childList: true });
        syncHiddenFromDOM();
    };
    window.chipsClear = () => {
        chipsObserver.disconnect();
        box.querySelectorAll('.nl-chip').forEach(chip => chip.remove());
        chipsObserver.observe(box, { childList: true });
        syncHiddenFromDOM();
    };
    addTokens(ta.value || '');

    input.addEventListener('keydown', (e) => {
        if (['Enter', 'Tab'].includes(e.key) || e.key === ',' || e.key === ';') {
            e.preventDefault();
            if (input.value.trim()) { addTokens(input.value); input.value = ''; }
        } else if (e.key === 'Backspace' && !input.value) {
            const last = box.querySelector('.nl-chip:last-of-type');
            if (last) { last.remove(); syncHiddenFromDOM(); }
        }
    });

    input.addEventListener('paste', (e) => {
        const text = (e.clipboardData || window.clipboardData).getData('text');
        if (/[,\n;\s]/.test(text)) { e.preventDefault(); addTokens(text); }
    });

    input.addEventListener('blur', () => {
        if (input.value.trim()) { addTokens(input.value); input.value = ''; }
    });

    box.addEventListener('click', (e) => {
        const btn = e.target.closest('.remove');
        if (!btn) return;
        const chip = btn.closest('.nl-chip');
        if (chip) { chip.remove(); syncHiddenFromDOM(); }
    });

    const chipsObserver = new MutationObserver(syncHiddenFromDOM);
    chipsObserver.observe(box, { childList: true });

    document.getElementById('sendEmailBtn')?.addEventListener('click', () => {
        if (input.value.trim()) { addTokens(input.value); input.value = ''; }
        syncHiddenFromDOM();
    });

    syncHiddenFromDOM();
})();
