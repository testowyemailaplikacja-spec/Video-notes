/* Offline browser-only controller. Never sends media/transcript over network. */
(function () {
  "use strict";
  var core = window.VideoNotesWebCore;
  if (!core) return;
  var PAGE_SIZE = 75;
  var doc = null;
  var edits = Object.create(null);
  var matches = [];
  var selected = null;
  var page = 0;
  var get = function (id) { return document.getElementById(id); };
  var elements = {
    source: get("source-file"), status: get("status"), search: get("search"),
    count: get("match-count"), edits: get("edit-count"), rows: get("segment-rows"),
    previous: get("previous"), next: get("next"), page: get("page-number"),
    selected: get("selected-label"), text: get("edit-text"), save: get("save-edit")
  };
  function message(text, error) {
    elements.status.textContent = text;
    elements.status.classList.toggle("error", Boolean(error));
  }
  function current(item) {
    return Object.prototype.hasOwnProperty.call(edits, item.id) ? edits[item.id] : item.text;
  }
  function setSelected(index) {
    if (!doc) return;
    var item = doc.segments[index];
    if (!item) return;
    selected = index;
    elements.selected.textContent = "Segment " + item.id + " · " +
      core.clock(item.start_ms, true).slice(0, 8);
    elements.text.value = current(item);
    elements.text.disabled = false;
    elements.save.disabled = false;
    renderList();
  }
  function renderList() {
    elements.rows.replaceChildren();
    if (!doc) return;
    var length = matches.length;
    var totalPages = Math.max(1, Math.ceil(length / PAGE_SIZE));
    page = Math.max(0, Math.min(page, totalPages - 1));
    for (var index of matches.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)) {
      var item = doc.segments[index];
      var row = document.createElement("tr");
      if (index === selected) row.className = "selected-row";
      var time = document.createElement("td");
      time.textContent = core.clock(item.start_ms, true).slice(0, 8);
      var body = document.createElement("td");
      var select = document.createElement("button");
      select.className = "segment-choice";
      select.type = "button";
      select.textContent = current(item);
      select.setAttribute("aria-label", "Edytuj segment " + item.id);
      select.addEventListener("click", function (number) {
        return function () { setSelected(number); };
      }(index));
      body.appendChild(select);
      row.append(time, body);
      elements.rows.appendChild(row);
    }
    if (!length) {
      var empty = document.createElement("tr");
      var cell = document.createElement("td");
      cell.colSpan = 2;
      cell.textContent = "Brak wypowiedzi dla podanej frazy.";
      empty.appendChild(cell);
      elements.rows.appendChild(empty);
    }
    elements.count.textContent = String(length) + " z " + doc.segments.length + " wypowiedzi";
    elements.edits.textContent = String(Object.keys(edits).length) + " poprawek w pamięci";
    elements.page.textContent = "Strona " + String(page + 1) + " / " + String(totalPages);
    elements.previous.disabled = page === 0;
    elements.next.disabled = page + 1 >= totalPages;
  }
  function filter() {
    if (!doc) return;
    matches = core.search(doc, edits, elements.search.value);
    page = 0;
    renderList();
  }
  elements.previous.addEventListener("click", function () {
    if (page > 0) { page -= 1; renderList(); }
  });
  elements.next.addEventListener("click", function () {
    if (page < Math.ceil(matches.length / PAGE_SIZE) - 1) { page += 1; renderList(); }
  });
  elements.search.addEventListener("input", filter);
  elements.save.addEventListener("click", function () {
    if (!doc || selected === null) return;
    var text = elements.text.value;
    if (text.length > core.MAX_TEXT || text.includes("\u0000")) {
      message("Poprawka jest zbyt długa lub zawiera niedozwolony znak.", true);
      return;
    }
    var item = doc.segments[selected];
    if (text === item.text) delete edits[item.id];
    else edits[item.id] = text;
    matches = core.search(doc, edits, elements.search.value);
    renderList();
    message("Poprawkę zachowano tylko w pamięci strony. Pobierz plik, aby nie utracić zmian.", false);
  });
  elements.source.addEventListener("change", async function (event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    try {
      if (file.size > core.MAX_BYTES) throw new Error("Wybrany JSON przekracza limit 20 MB.");
      var content = await file.text();
      var loaded = core.parseExport(content);
      doc = loaded;
      edits = Object.create(null);
      selected = null;
      page = 0;
      matches = core.search(doc, edits, "");
      elements.search.value = "";
      elements.search.disabled = false;
      elements.text.disabled = true;
      elements.text.value = "";
      elements.save.disabled = true;
      elements.selected.textContent = "Wybierz wiersz transkrypcji.";
      document.querySelectorAll("button[data-export]").forEach(function (button) {
        button.disabled = false;
      });
      renderList();
      message("Otworzono lokalnie " + file.name + " · " + loaded.segments.length +
        " segmentów · " + (loaded.complete ? "transkrypcja ukończona" : "transkrypcja niepełna") +
        ". Dane nie zostały wysłane do serwera.", false);
    } catch (error) {
      message("Nie można otworzyć pliku: " + error.message, true);
    } finally {
      elements.source.value = "";
    }
  });
  document.querySelectorAll("button[data-export]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!doc) return;
      var filename = button.getAttribute("data-export");
      try {
        var files = core.renderExports(doc, edits);
        var mime = filename.endsWith(".json") ? "application/json;charset=utf-8" :
          "text/plain;charset=utf-8";
        var blob = new Blob([files[filename]], {type: mime});
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        message("Przygotowano lokalnie " + filename + ". Zachowaj pobrany plik, aby nie utracić zmian.", false);
      } catch (error) {
        message("Eksport nie powiódł się: " + error.message, true);
      }
    });
  });
})();
