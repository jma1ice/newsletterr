/*
 * Mobile builder navigation (index page only). On narrow viewports the three
 * builder columns (config-row / preview-row / content-row) are stacked and a
 * bottom tab bar switches which one is visible.
 *
 * Non-destructive: the columns already carry `.mobile-content-panel` and
 * `.mobile-section-*` classes in the markup, and switching tabs only toggles
 * `.active`. The old version rebuilt `.container-fluid` innerHTML, which
 * destroyed every event listener the other builder scripts had bound; that
 * approach (organizeMobileContent / restoreOriginalContent / originalContent)
 * is gone.
 */
document.addEventListener('DOMContentLoaded', function () {
    if (window.innerWidth <= 768) {
        initializeMobileNavigation();
    }

    let resizeTimer;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            if (window.innerWidth <= 768) {
                if (!document.querySelector('.mobile-nav-container')) {
                    initializeMobileNavigation();
                }
            } else {
                removeMobileNavigation();
            }
        }, 250);
    });
});

function initializeMobileNavigation() {
    // Only build the tab bar where the builder columns exist.
    if (!document.getElementById('config-row')) {
        return;
    }

    const navContainer = document.createElement('div');
    navContainer.className = 'mobile-nav-container';
    navContainer.innerHTML = `
        <ul class="mobile-nav-tabs">
            <li class="mobile-nav-tab">
                <button type="button" class="mobile-tab-btn active" data-target="config">
                    <span>Config</span>
                </button>
            </li>
            <li class="mobile-nav-tab">
                <button type="button" class="mobile-tab-btn" data-target="preview">
                    <span>Preview</span>
                </button>
            </li>
            <li class="mobile-nav-tab">
                <button type="button" class="mobile-tab-btn" data-target="content">
                    <span>Content</span>
                </button>
            </li>
        </ul>
    `;

    const footer = document.querySelector('footer');
    if (footer) {
        footer.parentNode.insertBefore(navContainer, footer);
    } else {
        document.body.appendChild(navContainer);
    }

    setupTabHandlers();
    showMobileSection('config');
}

function setupTabHandlers() {
    document.querySelectorAll('.mobile-tab-btn').forEach(button => {
        button.addEventListener('click', function () {
            showMobileSection(this.getAttribute('data-target'));
        });
    });
}

function showMobileSection(target) {
    document.querySelectorAll('.mobile-tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-target') === target);
    });
    document.querySelectorAll('.builder-col.mobile-content-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    const panel = document.querySelector('.mobile-section-' + target);
    if (panel) {
        panel.classList.add('active');
    }
}

function removeMobileNavigation() {
    const navContainer = document.querySelector('.mobile-nav-container');
    if (navContainer) {
        navContainer.remove();
    }
}

function addTouchImprovements() {
    document.addEventListener('touchstart', function(e) {
        if (e.target.matches('.nl-btn, .btn, .mobile-tab-btn')) {
            e.target.style.opacity = '0.8';
        }
    });

    document.addEventListener('touchend', function(e) {
        if (e.target.matches('.nl-btn, .btn, .mobile-tab-btn')) {
            setTimeout(() => {
                e.target.style.opacity = '';
            }, 150);
        }
    });

    let lastTouchEnd = 0;
    document.addEventListener('touchend', function(e) {
        const now = (new Date()).getTime();
        if (now - lastTouchEnd <= 300) {
            if (e.target.matches('.nl-btn, .btn, input, select, textarea')) {
                e.preventDefault();
            }
        }
        lastTouchEnd = now;
    }, false);
}

addTouchImprovements();

window.MobileNavigation = {
    show: showMobileSection,
    remove: removeMobileNavigation
};

console.log('Mobile navigation script loaded');
