/**
 * Form submit button spinner — prevents double-submit.
 * On form submit, disables the submit button and shows a spinner.
 * Re-enables on pageshow (handles browser back button).
 */
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('form').forEach(function(form) {
        form.addEventListener('submit', function() {
            var btn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (!btn) return;
            if (btn.dataset.noSpinner) return;
            // Small delay to allow form submission to proceed
            setTimeout(function() {
                btn.disabled = true;
                if (btn.tagName === 'BUTTON') {
                    btn.dataset.originalText = btn.innerHTML;
                    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Sparar...';
                }
            }, 0);
        });
    });

    // Re-enable buttons when navigating back (bfcache)
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) {
            document.querySelectorAll('button[type="submit"][disabled], input[type="submit"][disabled]').forEach(function(btn) {
                btn.disabled = false;
                if (btn.dataset.originalText) {
                    btn.innerHTML = btn.dataset.originalText;
                    delete btn.dataset.originalText;
                }
            });
        }
    });
});
