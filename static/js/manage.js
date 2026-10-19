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
      area.dispatchEvent(new Event("input", { bubbles: true }));
      area.focus();
    });
  });

  /* -- Media library ----------------------------------------------------- */

  // The Markdown sits in a read-only field the administrator can select by
  // hand; the Copy button is a shortcut, so it stays hidden without script.
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    var source = button.parentElement.querySelector("[data-copy-source]");
    if (!source) return;
    button.hidden = false;
    button.addEventListener("click", function () {
      source.select();
      var done = function () {
        button.textContent = "Copied";
        window.setTimeout(function () { button.textContent = "Copy"; }, 1500);
      };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(source.value).then(done, function () {
          document.execCommand("copy");
          done();
        });
      } else {
        document.execCommand("copy");
        done();
      }
    });
  });

  // Filters apply as soon as a dropdown changes; the Apply button is only
  // needed without script.
  document.querySelectorAll("form[data-autosubmit]").forEach(function (form) {
    form.querySelectorAll("[data-autosubmit-hide]").forEach(function (el) {
      el.hidden = true;
    });
    // Leave unset filters out of the address, so it stays short to share.
    form.addEventListener("formdata", function (event) {
      Array.from(event.formData.entries()).forEach(function (pair) {
        if (!pair[1]) event.formData.delete(pair[0]);
      });
    });
    form.querySelectorAll("select").forEach(function (select) {
      select.addEventListener("change", function () {
        // A new filter starts back on page one.
        var page = form.querySelector("input[name='page']");
        if (page) page.remove();
        form.requestSubmit ? form.requestSubmit() : form.submit();
      });
    });
  });

  // "/" jumps to the library search, as on most sites with a search box.
  var search = document.getElementById("library-q");
  if (search) {
    document.addEventListener("keydown", function (event) {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      var target = event.target;
      if (target.closest("input, textarea, select, [contenteditable='true']")) return;
      event.preventDefault();
      search.focus();
      search.select();
    });
  }

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  /* -- Library picker ---------------------------------------------------- */

  // Without script each file shows its Markdown to copy; with it, Insert puts
  // that Markdown into the notes and the list can be searched and filtered.
  document.querySelectorAll("[data-library-picker]").forEach(function (picker) {
    var area = document.getElementById(picker.dataset.target);
    if (!area) return;

    // Until the administrator has clicked into the notes the cursor sits at
    // the very start, so an insert then goes to the end instead.
    var placed = false;
    area.addEventListener("focus", function () { placed = true; }, { once: true });

    picker.querySelectorAll("[data-picker-tools], [data-insert]").forEach(function (el) {
      el.hidden = false;
    });
    picker.querySelectorAll("[data-picker-fallback]").forEach(function (el) {
      el.hidden = true;
    });

    picker.querySelectorAll("[data-insert]").forEach(function (button) {
      button.addEventListener("click", function () {
        var start = placed ? area.selectionStart : area.value.length;
        var end = placed ? area.selectionEnd : area.value.length;
        var before = area.value.slice(0, start);
        var after = area.value.slice(end);
        // Its own paragraph, so a player or figure is not run into a sentence.
        var text = button.dataset.insert;
        if (before && !/\n\n$/.test(before)) text = (/\n$/.test(before) ? "\n" : "\n\n") + text;
        if (after && !/^\n\n/.test(after)) text += /^\n/.test(after) ? "\n" : "\n\n";
        area.setRangeText(text, start, end, "end");
        placed = true;
        area.dispatchEvent(new Event("input", { bubbles: true }));
        area.focus();

        var label = button.textContent;
        button.textContent = "Inserted";
        window.setTimeout(function () { button.textContent = label; }, 1500);
      });
    });

    // "Show" selects the line that links to a file, so it is easy to find,
    // move or delete. Hidden for files linked only from the quiz.
    picker.querySelectorAll("[data-find]").forEach(function (button) {
      var prefix = button.dataset.find;
      button.hidden = area.value.indexOf(prefix) === -1;
      button.addEventListener("click", function () {
        var at = area.value.indexOf(prefix);
        if (at === -1) return;
        var lineStart = area.value.lastIndexOf("\n", at) + 1;
        var lineEnd = area.value.indexOf("\n", at);
        area.focus();
        area.setSelectionRange(lineStart, lineEnd === -1 ? area.value.length : lineEnd);
        placed = true;
      });
    });

    var search = picker.querySelector("[data-picker-search]");
    var purposes = picker.querySelectorAll("[data-picker-purpose]");
    var items = picker.querySelectorAll("[data-picker-item]");
    var empty = picker.querySelector("[data-picker-empty]");
    var purpose = "";

    var apply = function () {
      var words = search ? search.value.toLowerCase().split(/\s+/).filter(Boolean) : [];
      var shown = 0;
      items.forEach(function (item) {
        var match = (!purpose || item.dataset.purpose === purpose) &&
          words.every(function (word) { return item.dataset.search.indexOf(word) !== -1; });
        item.hidden = !match;
        if (match) shown += 1;
      });
      if (empty) empty.hidden = shown > 0;
    };

    if (search) search.addEventListener("input", apply);
    purposes.forEach(function (button) {
      button.addEventListener("click", function () {
        purpose = button.dataset.pickerPurpose;
        purposes.forEach(function (other) {
          other.setAttribute("aria-pressed", String(other === button));
        });
        apply();
      });
    });
  });

  /* -- Unsaved changes --------------------------------------------------- */

  // Long editors warn before leaving with edits not yet saved, and say so
  // beside the Save button.
  document.querySelectorAll("form[data-dirty-guard]").forEach(function (form) {
    var note = document.querySelector("[data-dirty-note]");
    var dirty = false;
    var warn = function (event) {
      event.preventDefault();
      event.returnValue = "";
    };
    form.addEventListener("input", function (event) {
      // The picker's search box is not part of the module.
      if (dirty || event.target.matches("[data-picker-search]")) return;
      dirty = true;
      if (note) note.hidden = false;
      window.addEventListener("beforeunload", warn);
    });
    form.addEventListener("submit", function () {
      window.removeEventListener("beforeunload", warn);
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
