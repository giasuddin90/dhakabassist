/* Administration panel enhancements.
 *
 * Loaded only on /manage/ pages. Everything here is optional: the module
 * order can be saved with the button, and the Markdown toolbar just inserts
 * text the administrator could type.
 */
(function () {
  "use strict";

  /* -- Drag to reorder modules ------------------------------------------ */

  // Rows carry a hidden input, so the order posts with the form whether or
  // not dragging is available.
  var body = document.querySelector("[data-sortable]");
  if (body) {
    var dragged = null;

    body.addEventListener("dragstart", function (event) {
      dragged = event.target.closest("tr");
      if (!dragged) return;
      event.dataTransfer.effectAllowed = "move";
      // Firefox needs data set for a drag to begin at all.
      event.dataTransfer.setData("text/plain", dragged.dataset.pk || "");
      dragged.style.opacity = "0.4";
    });

    body.addEventListener("dragend", function () {
      if (dragged) dragged.style.opacity = "";
      dragged = null;
    });

    body.addEventListener("dragover", function (event) {
      if (!dragged) return;
      event.preventDefault();
      var over = event.target.closest("tr");
      if (!over || over === dragged) return;
      var box = over.getBoundingClientRect();
      var after = event.clientY > box.top + box.height / 2;
      body.insertBefore(dragged, after ? over.nextSibling : over);
    });
  }

  /* -- Markdown toolbar -------------------------------------------------- */

  var SNIPPETS = {
    H2: ["## ", ""],
    B: ["**", "**"],
    I: ["*", "*"],
    List: ["- ", ""],
    Link: ["[", "](https://)"],
    Image: ["![", "](notation/figure.svg)"],
    Audio: ["<audio controls src=\"", "\"></audio>"],
  };

  document.querySelectorAll("[data-md-tool]").forEach(function (button) {
    button.addEventListener("click", function () {
      var area = document.getElementById(button.dataset.mdTarget);
      var pair = SNIPPETS[button.dataset.mdTool];
      if (!area || !pair) return;

      var start = area.selectionStart;
      var end = area.selectionEnd;
      var selected = area.value.slice(start, end);
      area.setRangeText(pair[0] + selected + pair[1], start, end, "end");
      if (!selected) {
        area.selectionStart = area.selectionEnd = start + pair[0].length;
      }
      area.focus();
    });
  });

  /* -- Question picker --------------------------------------------------- */

  // The quiz editor saves one question at a time, so switching away from
  // unsaved edits would lose them.
  var editor = document.querySelector("[data-question-form]");
  if (editor) {
    var dirty = false;
    editor.addEventListener("input", function () { dirty = true; });
    editor.addEventListener("submit", function () { dirty = false; });

    document.querySelectorAll("[data-question-link]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        if (!dirty) return;
        if (!window.confirm("Switch question and discard your unsaved changes?")) {
          event.preventDefault();
        }
      });
    });
  }
})();
