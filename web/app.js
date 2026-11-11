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
  var sourceRevision = 0;
  var patchRevision = 0;
  // Track new edits made while an asynchronous file import is in flight.
  var editRevision = 0;
  // Bounded in-memory history: a correction is recorded only when explicitly saved.
  var undoStack = [];
  var redoStack = [];
  var MAX_HISTORY = 100;
  var mediaUrl = null;
  var pendingSeekSeconds = null;
  var get = function (id) { return document.getElementById(id); };
  var elements = {
    source: get("source-file"), corrections: get("corrections-file"), status: get("status"), search: get("search"),
    count: get("match-count"), edits: get("edit-count"), rows: get("segment-rows"),
    previous: get("previous"), next: get("next"), page: get("page-number"),
    selected: get("selected-label"), text: get("edit-text"),
    save: get("save-edit"), reset: get("reset-edit"),
    undo: get("undo-edit"), redo: get("redo-edit"),
    media: get("source-media"), player: get("source-player"),
    seek: get("seek-segment"), jump: get("jump-playhead")
  };
  function message(text, error) {
    elements.status.textContent = text;
    elements.status.classList.toggle("error", Boolean(error));
  }
  function current(item) {
    return Object.prototype.hasOwnProperty.call(edits, item.id) ? edits[item.id] : item.text;
  }
  function hasPendingEdit() {
    return Boolean(doc && selected !== null &&
      elements.text.value !== current(doc.segments[selected]));
  }
  function hasUnsavedWork() {
    return Boolean(Object.keys(edits).length || hasPendingEdit());
  }
  function updateHistoryControls() {
    elements.undo.disabled = !undoStack.length;
    elements.redo.disabled = !redoStack.length;
  }
  function recordChange(id, before, after) {
    if (before === after) return;
    undoStack.push({id: id, before: before, after: after});
    if (undoStack.length > MAX_HISTORY) undoStack.shift();
    redoStack.length = 0;
    updateHistoryControls();
  }
  function clearHistory() {
    undoStack.length = 0;
    redoStack.length = 0;
    updateHistoryControls();
  }
  function setEditedValue(id, value) {
    var item = doc.segments.find(function (s) { return s.id === id; });
    if (!item) throw new Error("Brak segmentu w historii edycji.");
    if (value === item.text) delete edits[id];
    else edits[id] = value;
    if (selected !== null && doc.segments[selected].id === id) {
      elements.text.value = value;
    }
    matches = core.search(doc, edits, elements.search.value);
    renderList();
  }
  function travelHistory(source, target, operation) {
    if (!doc || !source.length) return;
    if (hasPendingEdit() && !window.confirm(
      "W edytorze jest niezapisany tekst. Czy odrzucić tę wersję i " + operation + " zapisaną poprawkę?"
    )) return;
    var item = source.pop();
    try {
      setEditedValue(item.id, operation === "cofnąć" ? item.before : item.after);
      target.push(item);
      editRevision += 1;
      updateHistoryControls();
      message(operation === "cofnąć" ? "Cofnięto jedną zapisaną poprawkę." : "Ponowiono jedną zapisaną poprawkę.", false);
    } catch (_error) {
      source.push(item);
      updateHistoryControls();
      message("Historia nie pasuje do obecnej transkrypcji. Niczego nie zmieniono.", true);
    }
  }

  // Media is never copied to the transcript, stored, or uploaded. File-backed
  // object URLs let browsers seek without loading an entire OBS video into JS RAM.
  function updateMediaControls() {
    elements.seek.disabled = !mediaUrl || selected === null;
    elements.jump.disabled = !mediaUrl || !doc || !(elements.player.readyState >= 1);
  }
  function clearMedia() {
    var previous = mediaUrl;
    mediaUrl = null;
    pendingSeekSeconds = null;
    if (typeof elements.player.pause === "function") elements.player.pause();
    elements.player.removeAttribute("src");
    elements.player.hidden = true;
    if (typeof elements.player.load === "function") elements.player.load();
    if (previous) URL.revokeObjectURL(previous);
    elements.media.value = "";
    updateMediaControls();
  }
  function tryMediaSeek() {
    if (!mediaUrl || pendingSeekSeconds === null || !(elements.player.readyState >= 1)) return;
    var seconds = pendingSeekSeconds;
    pendingSeekSeconds = null;
    if (Number.isFinite(elements.player.duration) && seconds > elements.player.duration + 0.1) {
      message("Czas segmentu wykracza poza wybrane nagranie. Sprawdź, czy wskazano właściwy plik.", true);
      return;
    }
    try {
      elements.player.currentTime = seconds;
      message("Przesunięto lokalny odtwarzacz do " + core.clock(Math.round(seconds * 1000), true) +
        ". Odtwarzanie uruchamiasz samodzielnie.", false);
    } catch (_error) {
      message("Nie można przejść do czasu segmentu w tym pliku.", true);
    }
  }
  elements.media.addEventListener("change", function (event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    if (!doc || !Number.isSafeInteger(file.size) || file.size <= 0) {
      message("Najpierw wybierz transkrypcję, a potem niepusty plik audio/wideo.", true);
      elements.media.value = "";
      return;
    }
    clearMedia();
    try {
      mediaUrl = URL.createObjectURL(file);
      elements.player.src = mediaUrl;
      elements.player.hidden = false;
      if (typeof elements.player.load === "function") elements.player.load();
      updateMediaControls();
      message("Wybrano nagranie lokalne. Nie jest weryfikowane automatycznie względem transkrypcji. " +
        "Odsłuch nie rozpocznie się bez Twojego działania.", false);
    } catch (_error) {
      clearMedia();
      message("Nie udało się otworzyć lokalnego pliku audio/wideo.", true);
    }
  });
  elements.player.addEventListener("loadedmetadata", function () {
    updateMediaControls();
    tryMediaSeek();
  });
  elements.player.addEventListener("error", function () {
    if (!mediaUrl) return;
    clearMedia();
    message("Przeglądarka nie obsługuje tego nagrania lub jego kodeka. " +
      "Wybierz obsługiwany WAV/MP3/MP4/WebM albo odtwarzaj je w aplikacji Windows.", true);
  });
  elements.seek.addEventListener("click", function () {
    if (!mediaUrl || !doc || selected === null) return;
    pendingSeekSeconds = doc.segments[selected].start_ms / 1000;
    tryMediaSeek();
    if (pendingSeekSeconds !== null) {
      message("Wczytywanie nagrania. Przejście nastąpi po odczycie metadanych.", false);
    }
  });
  elements.jump.addEventListener("click", function () {
    if (!mediaUrl || !doc || !(elements.player.readyState >= 1)) return;
    var seconds = elements.player.currentTime;
    if (!Number.isFinite(seconds) || seconds < 0 || seconds > 86400) {
      message("Odtwarzacz nie udostępnia prawidłowego czasu.", true);
      return;
    }
    var index = core.locateAtTime(doc.segments, Math.round(seconds * 1000));
    if (setSelected(index, true)) {
      message("Wybrano ostatnią rozpoczętą wypowiedź dla czasu " +
        core.clock(Math.round(seconds * 1000), true) +
        ". Nie potwierdza to zgodności nagrania z transkrypcją.", false);
    }
  });
  window.addEventListener("pagehide", clearMedia);
  function setSelected(index, reveal) {
    // Clicking the already-selected row (or jumping to its playback position)
    // must NEVER silently replace an in-progress textarea draft.
    if (index === selected && hasPendingEdit()) {
      if (reveal) {
        var visible = matches.indexOf(index);
        if (visible < 0) {
          elements.search.value = "";
          matches = core.search(doc, edits, "");
          visible = index;
        }
        page = Math.floor(visible / PAGE_SIZE);
        renderList(true);
      }
      return true;
    }
    if (index !== selected && hasPendingEdit() &&
        !window.confirm("W edytorze jest niezachowana poprawka. Odrzucić ją i przejść do innej wypowiedzi?")) return false;
    if (!doc) return;
    var item = doc.segments[index];
    if (!item) return false;
    if (reveal) {
      var found = matches.indexOf(index);
      if (found < 0) {
        elements.search.value = "";
        matches = core.search(doc, edits, "");
        found = index;
      }
      page = Math.floor(found / PAGE_SIZE);
    }
    selected = index;
    elements.selected.textContent = "Segment " + item.id + " · " +
      core.clock(item.start_ms, true).slice(0, 8);
    elements.text.value = current(item);
    elements.text.disabled = false;
    elements.save.disabled = false;
    elements.reset.disabled = false;
    updateMediaControls();
    renderList(true);
    return true;
  }
  function renderList(focusSelected) {
    elements.rows.replaceChildren();
    if (!doc) return;
    var length = matches.length;
    var totalPages = Math.max(1, Math.ceil(length / PAGE_SIZE));
    var focusTarget = null;
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
      select.setAttribute("aria-controls", "edit-text");
      select.setAttribute("aria-pressed", index === selected ? "true" : "false");
      if (index === selected) focusTarget = select;
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
    // Replacing tbody removes the clicked button. Restore keyboard focus after selecting.
    if (focusSelected && focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
  }
  function filter() {
    if (!doc) return;
    matches = core.search(doc, edits, elements.search.value);
    page = 0;
    renderList();
  }
  window.addEventListener("beforeunload", function (event) {
    if (!hasUnsavedWork()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  elements.previous.addEventListener("click", function () {
    if (page > 0) { page -= 1; renderList(); }
  });
  elements.next.addEventListener("click", function () {
    if (page < Math.ceil(matches.length / PAGE_SIZE) - 1) { page += 1; renderList(); }
  });
  elements.search.addEventListener("input", filter);
  elements.text.addEventListener("input", function () { editRevision += 1; });
  elements.save.addEventListener("click", function () {
    if (!doc || selected === null) return;
    var text = elements.text.value;
    if (text.length > core.MAX_TEXT || text.includes("\u0000")) {
      message("Poprawka jest zbyt długa lub zawiera niedozwolony znak.", true);
      return;
    }
    var item = doc.segments[selected];
    var before = current(item);
    editRevision += 1;
    if (text === item.text) delete edits[item.id];
    else edits[item.id] = text;
    recordChange(item.id, before, text);
    matches = core.search(doc, edits, elements.search.value);
    renderList();
    message("Poprawkę zachowano tylko w pamięci strony. Pobierz plik, aby nie utracić zmian.", false);
  });
  elements.reset.addEventListener("click", function () {
    if (!doc || selected === null) return;
    if (hasPendingEdit() && !window.confirm(
      "W edytorze jest niezapisana poprawka. Odrzucić ją i przywrócić tekst z importowanego pliku?"
    )) return;
    var item = doc.segments[selected];
    var before = current(item);
    editRevision += 1;
    delete edits[item.id];
    elements.text.value = item.text;
    recordChange(item.id, before, item.text);
    matches = core.search(doc, edits, elements.search.value);
    renderList();
    message("Przywrócono segment z importowanego pliku. Źródło na dysku pozostaje bez zmian.", false);
  });
  elements.undo.addEventListener("click", function () {
    travelHistory(undoStack, redoStack, "cofnąć");
  });
  elements.redo.addEventListener("click", function () {
    travelHistory(redoStack, undoStack, "ponowić");
  });
  elements.source.addEventListener("change", async function (event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    var revision = ++sourceRevision;
    var initialEditRevision = editRevision;
    if (hasUnsavedWork() &&
        !window.confirm("Masz niezapisane poprawki. Otwarcie nowego pliku je usunie. Kontynuować?")) {
      elements.source.value = "";
      return;
    }
    try {
      if (file.size > core.MAX_BYTES) throw new Error("Wybrany JSON przekracza limit 20 MB.");
      var content = await file.text();
      var loaded = core.parseExport(content);
      if (revision !== sourceRevision) return; // Older slow file read must not replace newer import.
      // A user may edit the open document WHILE the next file is being read.
      // An earlier confirmation cannot authorize discarding newer changes.
      if (editRevision !== initialEditRevision && hasUnsavedWork() &&
          !window.confirm("Podczas wczytywania pliku wprowadzono nowe poprawki. Odrzucić je i otworzyć nowy plik?")) {
        message("Import anulowany: zachowano poprawki w bieżącej transkrypcji.", false);
        return;
      }
      clearMedia(); // Do not silently align old audio against a different transcript.
      doc = loaded;
      edits = Object.create(null);
      clearHistory();
      selected = null;
      page = 0;
      matches = core.search(doc, edits, "");
      elements.search.value = "";
      elements.search.disabled = false;
      elements.corrections.disabled = false;
      elements.media.disabled = false;
      elements.text.disabled = true;
      elements.text.value = "";
      elements.save.disabled = true;
      elements.reset.disabled = true;
      elements.selected.textContent = "Wybierz wiersz transkrypcji.";
      document.querySelectorAll("button[data-export]").forEach(function (button) {
        button.disabled = false;
      });
      renderList();
      message("Otworzono lokalnie " + file.name + " · " + loaded.segments.length +
        " segmentów · " + (loaded.complete ? "transkrypcja ukończona" : "transkrypcja niepełna") +
        ". Dane nie zostały wysłane do serwera.", false);
    } catch (error) {
      if (revision === sourceRevision) message("Nie można otworzyć pliku: " + error.message, true);
    } finally {
      if (revision === sourceRevision) elements.source.value = "";
    }
  });

  // A saved correction pack is only applicable to the same source JSON and
  // never overwrites a later import or an edit made during asynchronous read.
  elements.corrections.addEventListener("change", async function (event) {
    var file = event.target.files && event.target.files[0];
    if (!file) return;
    var revision = ++patchRevision;
    var startSourceRevision = sourceRevision;
    var startEditRevision = editRevision;
    if (!doc) {
      message("Najpierw otwórz lokalną transkrypcję transcript.json.", true);
      elements.corrections.value = "";
      return;
    }
    if (hasUnsavedWork() &&
        !window.confirm("Masz bieżące poprawki. Zastąpić je zapisanymi poprawkami z pliku?")) {
      elements.corrections.value = "";
      return;
    }
    try {
      if (file.size > core.MAX_PATCH_BYTES) throw new Error("Paczka poprawek przekracza 20 MiB.");
      var payload = await file.text();
      if (revision !== patchRevision || startSourceRevision !== sourceRevision) return;
      var restored = core.parseCorrections(doc, payload);
      if (editRevision !== startEditRevision && hasUnsavedWork() &&
          !window.confirm("Podczas odczytu wprowadzono kolejne zmiany. Czy je odrzucić?")) {
        message("Zachowano późniejsze poprawki; przywracanie anulowano.", false);
        return;
      }
      edits = restored;
      clearHistory(); // A restored patch is a new editing baseline, not a fake history entry.
      editRevision += 1;
      matches = core.search(doc, edits, elements.search.value);
      page = 0;
      if (selected !== null) elements.text.value = current(doc.segments[selected]);
      renderList();
      message("Przywrócono " + Object.keys(edits).length +
        " poprawek tylko w pamięci. Pobierz plik, aby zapisać wynik.", false);
    } catch (error) {
      if (revision === patchRevision && startSourceRevision === sourceRevision) {
        message("Nie zastosowano poprawek: " + error.message, true);
      }
    } finally {
      if (revision === patchRevision) elements.corrections.value = "";
    }
  });
  document.querySelectorAll("button[data-export]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!doc) return;
      if (hasPendingEdit()) {
        message("Najpierw kliknij „Zachowaj poprawkę” w edytorze. Eksport nie obejmuje niezapisanej treści pola.", true);
        return;
      }
      var filename = button.getAttribute("data-export");
      try {
        if (filename === "web-corrections.json" && !Object.keys(edits).length) {
          message("Brak zapisanych poprawek do przeniesienia. Najpierw popraw tekst i zapisz zmianę.", false);
          return;
        }
        var payload = filename === "web-corrections.json" ?
          core.renderCorrections(doc, edits) : core.renderExport(doc, edits, filename);
        var mime = filename.endsWith(".json") ? "application/json;charset=utf-8" :
          "text/plain;charset=utf-8";
        var blob = new Blob([payload], {type: mime});
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
