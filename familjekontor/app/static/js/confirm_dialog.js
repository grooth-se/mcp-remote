document.addEventListener('click', function(e) {
    var target = e.target.closest('[data-confirm]');
    if (target && !confirm(target.dataset.confirm)) {
        e.preventDefault();
    }
});
