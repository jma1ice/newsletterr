/*
 * Minimal modal driver, loaded on every page from base.html. Replaces
 * bootstrap.bundle.min.js for the only Bootstrap JS feature the app used:
 * modals. Keeps the Bootstrap markup shape (.modal / .modal-dialog /
 * .modal-content) and the data-bs-* attributes, so templates are unchanged
 * except email_history, which opened its modal via the bootstrap.Modal API and
 * now calls window.NLModal.show() instead.
 *
 * Supports: data-bs-toggle="modal" + data-bs-target, data-bs-dismiss="modal",
 * backdrop click, Escape, and focus return. Exposes window.NLModal.
 */
(function () {
    function backdrop() {
        var bd = document.querySelector('.nl-modal-backdrop-el');
        if (!bd) {
            bd = document.createElement('div');
            bd.className = 'nl-modal-backdrop-el';
            document.body.appendChild(bd);
        }
        return bd;
    }

    function open(modal) {
        if (!modal || modal.classList.contains('show')) return;
        modal._nlReturnFocus = document.activeElement;
        backdrop().classList.add('show');
        document.body.classList.add('nl-modal-open');
        modal.style.display = 'block';
        modal.removeAttribute('aria-hidden');
        // reflow so the .show transition runs
        void modal.offsetHeight;
        modal.classList.add('show');
        var focusable = modal.querySelector('input, select, textarea, button:not([data-bs-dismiss])');
        if (focusable) focusable.focus();
    }

    function close(modal) {
        if (!modal || !modal.classList.contains('show')) return;
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden', 'true');
        modal.style.display = 'none';
        if (!document.querySelector('.modal.show')) {
            var bd = document.querySelector('.nl-modal-backdrop-el');
            if (bd) bd.remove();
            document.body.classList.remove('nl-modal-open');
        }
        var ret = modal._nlReturnFocus;
        if (ret && typeof ret.focus === 'function') ret.focus();
    }

    document.addEventListener('click', function (e) {
        var toggle = e.target.closest('[data-bs-toggle="modal"]');
        if (toggle) {
            e.preventDefault();
            open(document.querySelector(toggle.getAttribute('data-bs-target')));
            return;
        }
        var dismiss = e.target.closest('[data-bs-dismiss="modal"]');
        if (dismiss) {
            e.preventDefault();
            close(dismiss.closest('.modal'));
            return;
        }
        if (e.target.classList.contains('nl-modal-backdrop-el')) {
            var shown = document.querySelector('.modal.show');
            if (shown) close(shown);
            return;
        }
        // click on the modal shim outside the dialog
        if (e.target.classList.contains('modal') && e.target.classList.contains('show')) {
            close(e.target);
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            var shown = document.querySelector('.modal.show');
            if (shown) close(shown);
        }
    });

    window.NLModal = {
        show: function (id) { open(document.getElementById(id)); },
        hide: function (id) { close(document.getElementById(id)); }
    };
})();
