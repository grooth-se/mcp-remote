// Searchable select dropdowns using Choices.js

function initSearchableSelect(el) {
    if (el._choices) return;
    var instance = new Choices(el, {
        searchEnabled: true,
        shouldSort: false,
        placeholderValue: 'Sök...',
        searchPlaceholderValue: 'Skriv för att söka...',
        noResultsText: 'Inga träffar',
        itemSelectText: '',
        searchResultLimit: 20,
        removeItemButton: false
    });
    el._choices = instance;
    return instance;
}

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('select.searchable-select').forEach(function(el) {
        initSearchableSelect(el);
    });
});
