let popoutWindow = null;
let currentTimeRange = APP.currentTimeRange;

function getThemedEmailCSS() {
    const emailTheme = themeSettings.email_theme || 'newsletter_blue';
    const isDark = document.documentElement.classList.contains('dark');
    
    let bgColor, textColor, cardBg, borderColor, mutedColor;
    
    bgColor = themeSettings.background_color || '#333333';
    textColor = themeSettings.text_color || '#62a1a4';
    cardBg = '#2d2d2d';
    borderColor = '#404040';
    mutedColor = '#cccccc';
    
    const primaryColor = themeSettings.primary_color || '#8acbd4';
    const secondaryColor = themeSettings.secondary_color || '#222222';
    const accentColor = themeSettings.accent_color || '#62a1a4';
    const logoWidth = APP.logoWidthOr80;
    
    return `
        <style>
            @import url(https://fonts.googleapis.com/css?family=IBM+Plex+Sans:400,700&display=swap);

            :root {
                --email-bg: ${bgColor};
                --email-text: ${textColor};
                --email-primary: ${primaryColor};
                --email-secondary: ${secondaryColor};
                --email-accent: ${accentColor};
                --email-card-bg: ${cardBg};
                --email-border: ${borderColor};
                --email-muted: ${mutedColor};
            }
            
            body {
                margin: 0;
                padding: 0;
                font-family: 'IBM Plex Sans';
                background-color: var(--email-bg);
                line-height: 1.6;
                color: var(--email-text);
            }
            
            .email-container {
                width: 100%;
                background: var(--email-card-bg);
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                border: 1px solid var(--email-border);
            }
            
            .email-header {
                background: linear-gradient(135deg, var(--email-accent) 0%, var(--email-primary) 100%);
                color: white;
                padding: 10px 20px;
                text-align: center;
            }
            
            .email-logo {
                max-width: ${logoWidth}px;
                height: auto;
            }
            
            .email-title {
                font-size: 28px;
                font-weight: bold;
                margin: 0;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
            }
            
            .email-content {
                padding: 10px 15px;
                color: var(--email-text);
                background: var(--email-card-bg);
            }
            
            .email-footer {
                background: var(--email-secondary);
                padding: 20px;
                text-align: center;
                border-top: 3px solid var(--email-primary);
                color: var(--email-muted);
                font-size: 12px;
            }
            
            .email-footer a {
                color: var(--email-accent);
                text-decoration: none;
            }
            
            .stats-card {
                margin: 20px 0;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                border: 1px solid var(--email-border);
                position: relative;
            }
            
            .stats-bg-blur {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                filter: blur(5px) brightness(1);
                z-index: 0;
            }
            
            .stats-overlay {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.3);
                z-index: 1;
            }
            
            .stats-content {
                position: relative;
                z-index: 2;
            }
            
            .stats-header {
                background: var(--email-bg);
                color: var(--email-primary);
                padding: 15px;
                text-align: center;
                font-weight: bold;
                font-size: 18px;
            }
            
            .stats-table {
                width: 100%;
                border-collapse: collapse;
            }
            
            .stats-table th {
                padding: 12px;
                background: rgba(52, 58, 64, 0.9);
                color: white;
                font-weight: bold;
                border: none;
            }
            
            .stats-table td {
                padding: 12px;
                background: rgba(255, 255, 255, 0.5);
                color: #333;
                border-bottom: 1px solid rgba(222, 226, 230, 0.8);
            }
            
            .recently-added {
                background: var(--email-card-bg);
                padding-bottom: 10px;
                border-radius: 8px;
                margin: 20px 0;
                border: 1px solid var(--email-border);
            }
            
            .recently-added h2 {
                text-align: center;
                color: var(--email-text);
                margin-bottom: 10px;
                margin-top: 0;
            }
            
            .recommendations-block {
                margin: 30px 0;
                padding: 20px;
                background: var(--email-card-bg);
                border-radius: 8px;
                border: 1px solid var(--email-border);
            }
            
            .recommendations-block h2, .recommendations-block h3 {
                color: var(--email-text);
            }
            
            .chart-placeholder {
                margin: 20px 0;
                padding: 30px;
                background: var(--email-card-bg);
                border: 2px dashed var(--email-border);
                border-radius: 8px;
                text-align: center;
            }
            
            .chart-placeholder h3, .chart-placeholder p {
                color: var(--email-muted);
            }

            /* Hand-mirrored from build_email_css_from_theme (app/theme.py):
               the real email's responsive rules, so the phone/tablet preview
               widths trigger the same stacking recipients see. */
            .email-container {
                max-width: 800px;
                width: 100%;
                margin: 0 auto;
            }
            @media only screen and (max-width: 600px) {
                .email-container {
                    width: 100% !important;
                    max-width: 100% !important;
                    margin: 0 !important;
                }
                .email-logo {
                    max-width: 60px !important;
                    width: 60px !important;
                }
                .recently-added-table {
                    display: block !important;
                    width: 100% !important;
                    text-align: center !important;
                }
                .recently-added-row {
                    display: inline !important;
                }
                .recently-added-table td {
                    width: 30% !important;
                    padding: 6px !important;
                    display: inline-block !important;
                    vertical-align: top !important;
                    box-sizing: border-box !important;
                }
                .recently-added-card {
                    width: 100% !important;
                    max-width: 150px !important;
                    margin: 0 auto 10px auto !important;
                    height: auto !important;
                    overflow: hidden !important;
                    border-radius: 10px !important;
                }
                .card-content {
                    height: auto !important;
                    min-height: 165px !important;
                    text-align: left !important;
                }
            }
        </style>
    `;
}

// Device-size preview (NEWS-27): the chips narrow the preview iframe to real
// device widths so the email's own media queries apply. Shared by the pane
// and the pop-out window; the choice persists per session.
const PREVIEW_SIZES = { desktop: 800, tablet: 600, phone: 375 };

function currentPreviewSize() {
    const saved = sessionStorage.getItem('preview_size');
    return PREVIEW_SIZES[saved] ? saved : 'desktop';
}

function applyPreviewSize(name) {
    if (!PREVIEW_SIZES[name]) name = 'desktop';
    sessionStorage.setItem('preview_size', name);
    const frame = document.getElementById('preview');
    if (frame) {
        if (name === 'desktop') {
            frame.style.width = '100%';
        } else {
            frame.style.width = PREVIEW_SIZES[name] + 'px';
        }
        resizePreviewFrame(frame);
    }
    document.querySelectorAll('.preview-size-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.size === name));
    if (typeof popoutWindow !== 'undefined' && popoutWindow && !popoutWindow.closed) {
        try {
            popoutWindow.resizeTo(PREVIEW_SIZES[name] + 60, popoutWindow.outerHeight);
        } catch (_) {}
    }
}

document.querySelectorAll('.preview-size-btn').forEach(btn => {
    btn.addEventListener('click', () => applyPreviewSize(btn.dataset.size));
});
document.addEventListener('DOMContentLoaded', () => applyPreviewSize(currentPreviewSize()));

function resizePreviewFrame(frame) {
    try {
        const doc = frame.contentDocument || frame.contentWindow.document;
        if (doc && doc.body) {
            const contentHeight = Math.max(
                doc.body.scrollHeight,
                doc.body.offsetHeight,
                doc.documentElement.clientHeight,
                doc.documentElement.scrollHeight,
                doc.documentElement.offsetHeight
            );
            
            const minHeight = 480;
            const maxHeight = 1200;
            const newHeight = Math.max(minHeight, Math.min(maxHeight, contentHeight + 40));
            
            frame.style.height = newHeight + 'px';
        }
    } catch (e) {
        console.log('Could not resize iframe:', e);
    }
}

async function updatePreview() {
    try {
        if (document.getElementById('custom-html-toggle')?.checked) {
            const html = document.getElementById('custom-html-editor')?.value || '';
            const frame = document.getElementById('preview');
            if (frame) frame.srcdoc = html;
            return;
        }

        console.log('updatePreview called with selectedItems:', selectedItems);
        
        if (typeof selectedItems === 'undefined') {
            console.error('selectedItems is undefined in updatePreview');
            return;
        }
        
        const serverName = APP.serverName;
        const subject = document.getElementById('subject').value;
        const emailHeaderTitle = document.getElementById('email_header_title').value;
        const logoFilename = APP.logoFilename;
        const logoWidth = APP.logoWidthStr;
        const customLogoFilename = APP.customLogoFilename
        const logoPosition = APP.logoPosition;
        const themedCSS = getThemedEmailCSS();

        let contentHTML = "";
        
        for (let itemIndex = 0; itemIndex < selectedItems.length; itemIndex++) {
            const item = selectedItems[itemIndex];

            if (item.type === 'textblock') {
                const content = getTextBlockContent(item.id);
                if (content && content.trim().length > 0) {
                    const formattedContent = content.trim().replace(/\n/g, "<br>");
                    contentHTML += `<div style="margin-bottom: 15px; line-height: 1.6; text-align: center; color: var(--email-text);">${formattedContent}</div>`;
                }
            } else if (item.type === 'headerblock') {
                const content = getTextBlockContent(item.id);
                if (content && content.trim().length > 0) {
                    const formattedContent = content.trim().replace(/\n/g, "<br>");
                    contentHTML += `<div style="margin-bottom: 20px; font-size: 1.5em; font-weight: bold; text-align: center; color: var(--email-text);">${formattedContent}</div>`;
                }
            } else if (item.type === 'titleblock') {
                const content = getTextBlockContent(item.id);
                if (content && content.trim().length > 0) {
                    const formattedContent = content.trim().replace(/\n/g, "<br>");
                    contentHTML += `<div style="margin-bottom: 20px; font-size: 2em; font-weight: bold; text-align: center; color: var(--email-text);">${formattedContent}</div>`;
                }
            } else if (item.type === 'separator') {
                contentHTML += `<hr style="border: none; border-top: 1px solid var(--email-text); margin: 20px auto; width: 80%;">`;
            } else if (item.type === 'image' || item.type === 'gif') {
                if (item.src) {
                    const alignStyle = item.align === 'left' ? 'margin-right: auto;' 
                                    : item.align === 'right' ? 'margin-left: auto;' 
                                    : 'margin-left: auto; margin-right: auto;';
                    contentHTML += `
                        <div style="text-align: ${item.align || 'center'}; margin: 10px 0;">
                            <img src="${item.src}" 
                                width="${item.width || 400}"
                                style="display: block; max-width: 100%; height: auto; ${alignStyle}"
                                alt="">
                        </div>`;
                }
            } else if (item.type === 'emoji') {
                if (item.content) {
                    contentHTML += `
                        <div style="
                            text-align: ${item.align || 'center'};
                            font-size: ${item.size || '2em'};
                            line-height: 1.4;
                            margin: 10px 0;
                        ">${item.content}</div>`;
                }
            } else if (item.type === 'stat') {
                contentHTML += buildStatPreviewHTML(item.id);
            } else if (item.type === 'graph') {
                contentHTML += buildGraphPreviewHTML(item.id);
            } else if (item.type === 'recently added') {
                contentHTML += buildRecentlyAddedPreviewHTML(item.raLibrary, item.raCount);
            } else if (item.type === 'recommendations') {
                contentHTML += buildRecommendationsPreviewHTML(item.userKey);
            } else if (item.type === 'droppedneedle_wrapped') {
                contentHTML += buildDroppedNeedleWrappedPreviewHTML(item.userKey);
            } else if (item.type === 'droppedneedle_server_stats') {
                contentHTML += buildDroppedNeedleServerStatsPreviewHTML();
            } else if (item.type === 'yearly_wrapped') {
                contentHTML += buildYearlyWrappedPreviewHTML();
            } else if (item.type === 'sonarr_coming_soon') {
                contentHTML += buildSonarrComingSoonPreviewHTML();
            } else if (item.type === 'radarr_coming_soon') {
                contentHTML += buildRadarrComingSoonPreviewHTML();
            } else if (item.type === 'ombi_requests') {
                contentHTML += buildOmbiRequestsPreviewHTML();
            } else if (item.type === 'seerr_requests') {
                contentHTML += buildSeerrRequestsPreviewHTML();
            } else if (item.type === 'collection_group') {
                if (item.collections && item.collections.length > 0) {
                    const stableGroupId = item.id || `group-${itemIndex}`;
                    contentHTML += buildCollectionPreviewHTMLForEmail(
                        item.title || 'Collections',
                        item.collections,
                        stableGroupId
                    );
                }
            }
        }

        const hostedEnabled = APP.settings.hosted_enabled === 'enabled';
        const hostedLinksEnabled = APP.settings.hosted_links_enabled === 'enabled' && APP.settings.hosted_links_base_url;
        const linksBaseUrl = hostedLinksEnabled ? APP.settings.hosted_links_base_url : (APP.settings.hosted_base_url || '');
        const completeHTML = buildPreviewEmailHTML(contentHTML, serverName, subject, emailHeaderTitle, logoFilename, logoWidth, customLogoFilename, themedCSS, logoPosition, hostedEnabled, linksBaseUrl);
        
        const frame = document.getElementById('preview');
        if (!frame) {
            console.error('Preview iframe not found!');
            return;
        }
        
        frame.srcdoc = completeHTML;

        if (typeof popoutWindow !== 'undefined' && popoutWindow && !popoutWindow.closed) {
            try {
                popoutWindow.document.open();
                popoutWindow.document.write(completeHTML);
                popoutWindow.document.close();
                popoutWindow.document.title = 'Email Preview';
            } catch(e) {
                popoutWindow = null;
            }
        }
        
        frame.onload = function() {
            try {
                const doc = frame.contentDocument || frame.contentWindow.document;
                if (doc && doc.documentElement) {
                    resizePreviewFrame(frame);
                }
            } catch (e) {
                console.log('Could not resize iframe:', e);
            }
        };
        
        console.log('Preview updated successfully');
    } catch (error) {
        console.error('Error in updatePreview:', error);
        const frame = document.getElementById('preview');
        if (frame) {
            frame.srcdoc = `<html><body><p>Error updating preview: ${error.message}</p></body></html>`;
        }
    }
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

const debouncedUpdatePreview = debounce(updatePreview, 300);

document.getElementById('custom-html-toggle').addEventListener('change', function() {
    const isCustom = this.checked;
    document.getElementById('custom-html-pane').style.display = isCustom ? 'block' : 'none';
    document.getElementById('selected-items-list').style.display = isCustom ? 'none' : 'block';

    document.querySelectorAll('.mb-4').forEach(el => {
        if (el !== document.getElementById('custom-html-toggle-row')?.closest('.mb-4')) {
            el.style.display = isCustom ? 'none' : '';
        }
    });

    if (isCustom) {
        const editor = document.getElementById('custom-html-editor');
        editor.removeEventListener('input', debouncedUpdatePreview);
        editor.addEventListener('input', debouncedUpdatePreview);
    }

    updatePreview();
});

document.getElementById('custom-html-editor').addEventListener('input', debouncedUpdatePreview);
