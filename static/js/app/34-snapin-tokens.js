// Snap-in tokens in custom HTML (NEWS-32): the Insert snap-in picker above
// the custom HTML editor. Options are rebuilt on focus so libraries and stat
// titles enumerate whatever is currently cached; graphs are excluded (their
// images are captured client-side per builder item, which custom HTML lacks).
function buildSnapinTokenOptions() {
    const picker = document.getElementById('snapin-token-picker');
    if (!picker) return;

    const options = [];
    const raLibs = [...new Set((recentPayload || []).flatMap(x => x?.recently_added || []).map(i => i.library_name || i.section_name).filter(Boolean))].sort();
    raLibs.forEach(lib => options.push([`{{snapin:recently_added:${lib}}}`, `Recently Added: ${lib}`]));

    const mwLibs = [...new Set((mostWatchedPayload || []).flatMap(x => x?.most_watched || []).map(i => i.library_name).filter(Boolean))].sort();
    mwLibs.forEach(lib => options.push([`{{snapin:most_watched:${lib}}}`, `Most Watched: ${lib}`]));

    (randomPickLibraries || []).forEach(lib => options.push([`{{snapin:random_pick:${lib.title}}}`, `Random Pick: ${lib.title}`]));

    (typeof statsList !== 'undefined' ? statsList || [] : []).forEach(stat => {
        if (stat.stat_title) options.push([`{{snapin:stats:${stat.stat_title}}}`, `Stat: ${stat.stat_title}`]);
    });

    options.push(['{{snapin:wrapped}}', 'Year in Plex (wrapped)']);
    options.push(['{{snapin:coming_soon_tv}}', 'Coming Soon: TV']);
    options.push(['{{snapin:coming_soon_movies}}', 'Coming Soon: Movies']);
    options.push(['{{snapin:requests_ombi}}', 'Recent Requests (Ombi)']);
    options.push(['{{snapin:requests_seerr}}', 'Recent Requests (Seerr)']);
    options.push(['{{snapin:dn_server}}', 'DroppedNeedle Server Stats']);

    picker.innerHTML = '<option value="">Insert snap-in...</option>';
    options.forEach(([token, label]) => {
        const opt = document.createElement('option');
        opt.value = token;
        opt.textContent = label;
        picker.appendChild(opt);
    });
    const disabledNote = document.createElement('option');
    disabledNote.disabled = true;
    disabledNote.textContent = 'Graphs are not available as tokens';
    picker.appendChild(disabledNote);
}

function insertSnapinToken(token) {
    const editor = document.getElementById('custom-html-editor');
    if (!editor || !token) return;
    const start = editor.selectionStart ?? editor.value.length;
    const end = editor.selectionEnd ?? editor.value.length;
    editor.value = editor.value.slice(0, start) + token + editor.value.slice(end);
    const pos = start + token.length;
    editor.focus();
    editor.setSelectionRange(pos, pos);
    editor.dispatchEvent(new Event('input', { bubbles: true }));
}

document.addEventListener('DOMContentLoaded', () => {
    const picker = document.getElementById('snapin-token-picker');
    if (!picker) return;
    buildSnapinTokenOptions();
    picker.addEventListener('focus', buildSnapinTokenOptions);
    picker.addEventListener('change', () => {
        insertSnapinToken(picker.value);
        picker.value = '';
    });
});
