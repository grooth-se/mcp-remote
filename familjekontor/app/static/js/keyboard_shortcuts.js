/**
 * Keyboard shortcuts for Familjekontor.
 * Ctrl+S / Cmd+S — submit the first visible form
 * Escape — navigate back (Avbryt / Tillbaka)
 * Alt+N — navigate to "Ny" (new) action
 */
document.addEventListener('keydown', function(e) {
    // Ctrl+S / Cmd+S — submit form
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        var form = document.querySelector('form[method="POST"], form[method="post"]');
        if (form) {
            e.preventDefault();
            form.requestSubmit();
        }
    }

    // Escape — click back / cancel button
    if (e.key === 'Escape') {
        // Don't trigger if user is in a dropdown or modal
        if (document.querySelector('.modal.show, .dropdown-menu.show')) return;
        var back = document.querySelector('a.btn-secondary, a.btn-outline-secondary');
        if (back && (back.textContent.includes('Avbryt') || back.textContent.includes('Tillbaka'))) {
            back.click();
        }
    }

    // Ctrl+K / Cmd+K — focus global search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        var searchInput = document.getElementById('global-search-input');
        if (searchInput) {
            e.preventDefault();
            searchInput.focus();
            searchInput.select();
        }
    }

    // / — focus global search (when not in an input)
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        var tag = document.activeElement.tagName;
        if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT' && !document.activeElement.isContentEditable) {
            var searchInput2 = document.getElementById('global-search-input');
            if (searchInput2) {
                e.preventDefault();
                searchInput2.focus();
                searchInput2.select();
            }
        }
    }

    // Alt+N — navigate to "Ny" (new)
    if (e.altKey && e.key === 'n') {
        var links = document.querySelectorAll('a.btn-primary');
        for (var i = 0; i < links.length; i++) {
            if (links[i].textContent.includes('Ny') || links[i].innerHTML.includes('plus-circle')) {
                e.preventDefault();
                links[i].click();
                break;
            }
        }
    }
});

// Initialize Bootstrap tooltips
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function(el) {
        new bootstrap.Tooltip(el);
    });
});
