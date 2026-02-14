/**
 * Favorites management (Phase 7D)
 * Drag-and-drop reorder + inline label editing.
 */
(function() {
  'use strict';

  document.addEventListener('DOMContentLoaded', function() {
    var list = document.getElementById('favorites-list');
    if (!list) return;

    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    var csrf = csrfMeta ? csrfMeta.getAttribute('content') : '';
    var dragItem = null;

    // --- Drag and drop reorder ---
    list.addEventListener('dragstart', function(e) {
      dragItem = e.target.closest('li');
      if (dragItem) {
        dragItem.style.opacity = '0.5';
        e.dataTransfer.effectAllowed = 'move';
      }
    });

    list.addEventListener('dragend', function(e) {
      if (dragItem) dragItem.style.opacity = '';
      dragItem = null;
      // Remove all drag-over styles
      list.querySelectorAll('.drag-over').forEach(function(el) {
        el.classList.remove('drag-over');
      });
    });

    list.addEventListener('dragover', function(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      var target = e.target.closest('li');
      if (target && target !== dragItem) {
        list.querySelectorAll('.drag-over').forEach(function(el) {
          el.classList.remove('drag-over');
        });
        target.classList.add('drag-over');
      }
    });

    list.addEventListener('drop', function(e) {
      e.preventDefault();
      var target = e.target.closest('li');
      if (target && dragItem && target !== dragItem) {
        var items = Array.from(list.children);
        var dragIdx = items.indexOf(dragItem);
        var targetIdx = items.indexOf(target);
        if (dragIdx < targetIdx) {
          list.insertBefore(dragItem, target.nextSibling);
        } else {
          list.insertBefore(dragItem, target);
        }
        saveOrder();
      }
      list.querySelectorAll('.drag-over').forEach(function(el) {
        el.classList.remove('drag-over');
      });
    });

    function saveOrder() {
      var ids = [];
      list.querySelectorAll('li').forEach(function(li) {
        ids.push(parseInt(li.getAttribute('data-id')));
      });
      fetch('/favorites/reorder', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf,
        },
        body: JSON.stringify({ ids: ids }),
      });
    }

    // --- Inline label editing ---
    list.querySelectorAll('.fav-label').forEach(function(label) {
      label.addEventListener('click', function() {
        this.contentEditable = 'true';
        this.focus();
        // Select all text
        var range = document.createRange();
        range.selectNodeContents(this);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      });

      label.addEventListener('blur', function() {
        this.contentEditable = 'false';
        var favId = this.getAttribute('data-id');
        var newLabel = this.textContent.trim();
        if (newLabel) {
          fetch('/favorites/' + favId + '/update', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrf,
            },
            body: JSON.stringify({ label: newLabel }),
          });
        }
      });

      label.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.blur();
        }
      });
    });
  });
})();
