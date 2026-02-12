// Unsaved changes warning for forms with data-warn-unsaved attribute
document.addEventListener('DOMContentLoaded', function() {
    var forms = document.querySelectorAll('form[data-warn-unsaved]');
    forms.forEach(function(form) {
        var dirty = false;
        form.addEventListener('input', function() { dirty = true; });
        form.addEventListener('change', function() { dirty = true; });
        form.addEventListener('submit', function() { dirty = false; });
        window.addEventListener('beforeunload', function(e) {
            if (dirty) { e.preventDefault(); e.returnValue = ''; }
        });
    });
});
