(function() {
    const a = document.getElementById('alert_p');
    const e = document.getElementById('error_p');
    if (a && a.textContent.trim()) a.style.display = '';
    if (e && e.textContent.trim()) e.style.display = '';
})();
