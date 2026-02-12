// Back to top - floating button
document.addEventListener('DOMContentLoaded', function() {
    var btn = document.createElement('button');
    btn.innerHTML = '<i class="bi bi-arrow-up"></i>';
    btn.className = 'btn btn-secondary btn-sm back-to-top';
    btn.setAttribute('aria-label', 'Tillbaka till toppen');
    btn.style.display = 'none';
    document.body.appendChild(btn);

    btn.addEventListener('click', function() {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    window.addEventListener('scroll', function() {
        btn.style.display = window.scrollY > 300 ? '' : 'none';
    });
});
