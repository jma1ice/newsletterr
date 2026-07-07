document.getElementById('time_range_week').addEventListener('click', () => {
    document.getElementById('days_to_pull').value = 7;
    document.getElementById('stats_form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
});
document.getElementById('time_range_month').addEventListener('click', () => {
    document.getElementById('days_to_pull').value = 30;
    document.getElementById('stats_form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
});
document.getElementById('time_range_quarter').addEventListener('click', () => {
    document.getElementById('days_to_pull').value = 90;
    document.getElementById('stats_form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
});
document.getElementById('time_range_two_q').addEventListener('click', () => {
    document.getElementById('days_to_pull').value = 180;
    document.getElementById('stats_form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
});
document.getElementById('time_range_three_q').addEventListener('click', () => {
    document.getElementById('days_to_pull').value = 270;
    document.getElementById('stats_form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
});
document.getElementById('time_range_year').addEventListener('click', () => {
    document.getElementById('days_to_pull').value = 365;
    document.getElementById('stats_form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
});
