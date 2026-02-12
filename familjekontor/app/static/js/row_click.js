/**
 * Clickable table rows — navigates to URL in data-row-link attribute.
 * Ignores clicks on interactive elements (buttons, links, inputs).
 */
document.addEventListener('click', function(e) {
    var row = e.target.closest('tr[data-row-link]');
    if (!row) return;

    // Don't navigate if clicking on interactive elements
    var tag = e.target.tagName.toLowerCase();
    if (tag === 'a' || tag === 'button' || tag === 'input' || tag === 'select') return;
    if (e.target.closest('a, button, input, select, form')) return;

    window.location.href = row.dataset.rowLink;
});
