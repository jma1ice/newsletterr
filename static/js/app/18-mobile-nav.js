document.addEventListener('DOMContentLoaded', function() {
    
    if (window.innerWidth <= 768) {
        initializeMobileNavigation();
        organizeMobileContent();
    }
    
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            if (window.innerWidth <= 768) {
                if (!document.querySelector('.mobile-nav-container')) {
                    initializeMobileNavigation();
                    organizeMobileContent();
                }
            } else {
                removeMobileNavigation();
                restoreOriginalContent();
            }
        }, 250);
    });
});

function initializeMobileNavigation() {
    console.log('Initializing mobile navigation...');
    
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
        document.body.insertBefore(navContainer, footer);
    } else {
        document.body.appendChild(navContainer);
    }
    
    setupTabHandlers();
}

function setupTabHandlers() {
    const tabButtons = document.querySelectorAll('.mobile-tab-btn');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const target = this.getAttribute('data-target');
            
            document.querySelectorAll('.mobile-tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            document.querySelectorAll('.mobile-content-panel').forEach(panel => {
                panel.classList.remove('active');
            });
            
            this.classList.add('active');
            const panel = document.querySelector(`.mobile-section-${target}`);
            if (panel) {
                panel.classList.add('active');
            }
            
            console.log(`Switched to ${target} tab`);
        });
    });
}

function organizeMobileContent() {
    console.log('Organizing mobile content by table row IDs...');
    
    const containerFluid = document.querySelector('.container-fluid');
    if (!containerFluid) {
        console.warn('Container fluid not found');
        return;
    }
    
    if (!window.originalContent) {
        window.originalContent = containerFluid.innerHTML;
    }

    const welcomeMessage = document.getElementById('welcome-message');
    const sendEmailBtn = document.getElementById('sendEmailBtn');
    
    const configRow = document.getElementById('config-row');
    const previewRow = document.getElementById('preview-row');
    const contentRow = document.getElementById('content-row');
    
    if (!configRow || !contentRow || !previewRow) {
        console.warn('Could not find all table rows with IDs');
        console.log('Config row:', !!configRow);
        console.log('Preview row:', !!previewRow);
        console.log('Content row:', !!contentRow);
        return;
    }
    
    containerFluid.innerHTML = `
        <div class="mobile-content-panel mobile-section-config active">
            <div style="width: 100%; overflow-x: auto;">
                ${welcomeMessage.outerHTML}
                <table style="width: 100%;">
                    <tbody>
                        ${configRow.outerHTML}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="mobile-content-panel mobile-section-preview">
            <div style="width: 100%; overflow-x: auto;">
                <table style="width: 100%;">
                    <tbody>
                        ${previewRow.outerHTML}
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="mobile-content-panel mobile-section-content">
            <div style="width: 100%; overflow-x: auto;">
                ${sendEmailBtn.outerHTML}
                <table style="width: 100%;">
                    <tbody>
                        ${contentRow.outerHTML}
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    console.log('Successfully organized content by table row IDs');
}

function removeMobileNavigation() {
    const navContainer = document.querySelector('.mobile-nav-container');
    if (navContainer) {
        navContainer.remove();
    }
}

function restoreOriginalContent() {
    console.log('Restoring original content for desktop...');
    
    const containerFluid = document.querySelector('.container-fluid');
    if (!containerFluid) return;
    
    const panels = document.querySelectorAll('.mobile-content-panel');
    panels.forEach(panel => {
        panel.classList.remove('mobile-content-panel', 'mobile-section-config', 'mobile-section-content', 'mobile-section-preview', 'active');
        panel.style.display = 'block';
    });
    
    if (window.originalContent) {
        containerFluid.innerHTML = window.originalContent;
    }
}

function addTouchImprovements() {
    document.addEventListener('touchstart', function(e) {
        if (e.target.matches('.button, .btn, .mobile-tab-btn')) {
            e.target.style.opacity = '0.8';
        }
    });
    
    document.addEventListener('touchend', function(e) {
        if (e.target.matches('.button, .btn, .mobile-tab-btn')) {
            setTimeout(() => {
                e.target.style.opacity = '';
            }, 150);
        }
    });
    
    let lastTouchEnd = 0;
    document.addEventListener('touchend', function(e) {
        const now = (new Date()).getTime();
        if (now - lastTouchEnd <= 300) {
            if (e.target.matches('.button, .btn, input, select, textarea')) {
                e.preventDefault();
            }
        }
        lastTouchEnd = now;
    }, false);
}

addTouchImprovements();

window.MobileNavigation = {
    organize: organizeMobileContent,
    remove: removeMobileNavigation,
    restore: restoreOriginalContent
};

console.log('Mobile navigation script loaded');
