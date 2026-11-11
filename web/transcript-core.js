/* Video Notes / KWN — standalone offline browser import and export.
 * CommonJS for tests; simple script for file:// browser use (no servers/CORS).
 * No external dependencies, storage, network or telemetry.
 */
(function (root) {
  "use strict";
  var SCHEMA = "videonotes-export-v1";
  var MAX_BYTES = 20 * 1024 * 1024;
  var MAX_SEGMENTS = 50000;
  var MAX_TEXT = 10000;
  // Output cap is independent of the 20 MiB imported source limit:
  // up to 50k independently edited 10k-character segments could otherwise
  // trigger a hundreds-of-megabytes Blob/string allocation.
  var MAX_OUTPUT_BYTES = 64 * 1024 * 1024;
  // Desktop import-web-edits accepts at most 20 MiB.
  var MAX_PATCH_BYTES = 20 * 1024 * 1024;
  function exportTooLarge(limit) {
    reject("Eksport przekroczył limit " + (limit / (1024 * 1024)) +
      " MiB. Podziel transkrypcję lub skróć poprawki; oryginał i edycje pozostają bez zmian.");
  }
  // Conservative, constant-memory preflight before constructing huge output strings.
  // The count includes per-segment JSON/cue overhead; after rendering a precise
  // UTF-8 byte check catches escaping and non-ASCII expansion.
  function checkBudget(doc, edits, patchOnly) {
    var size = 128;
    for (var item of doc.segments) {
      var edited = Object.prototype.hasOwnProperty.call(edits, item.id) ? edits[item.id] : item.text;
      if (patchOnly && edited === item.text) continue;
      size += 256 + edited.length + (patchOnly ? item.text.length : 0);
      if (size > (patchOnly ? MAX_PATCH_BYTES : MAX_OUTPUT_BYTES)) exportTooLarge(patchOnly ? MAX_PATCH_BYTES : MAX_OUTPUT_BYTES);
    }
  }
  function utf8BytesUnderLimit(payload, limit) {
    limit = limit || MAX_OUTPUT_BYTES;
    if (payload.length > limit) exportTooLarge(limit);
    var count = 0;
    for (var i = 0; i < payload.length; i++) {
      var ch = payload.charCodeAt(i);
      if (ch < 0x80) count++;
      else if (ch < 0x800) count += 2;
      else if (ch >= 0xd800 && ch <= 0xdbff &&
               i + 1 < payload.length &&
               payload.charCodeAt(i + 1) >= 0xdc00 &&
               payload.charCodeAt(i + 1) <= 0xdfff) { count += 4; i++; }
      else count += 3;
      if (count > limit) exportTooLarge(limit);
    }
    return payload;
  }

  function reject(message) { throw new Error(message); }
  function plainObject(value) {
    return value !== null && typeof value === "object" &&
      !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype ||
      Object.getPrototypeOf(value) === null);
  }
  function validText(value, size) {
    return typeof value === "string" && value.length <= size && !value.includes("\u0000");
  }
  function validTime(value) {
    return Number.isSafeInteger(value) && value >= 0 && value <= 24 * 3600 * 1000;
  }
  function validateExport(value) {
    if (!plainObject(value) || value.schema !== SCHEMA ||
        !validText(value.project_id, 128) || !value.project_id.trim() ||
        !["pl", "en", "auto"].includes(value.language) ||
        typeof value.complete !== "boolean" ||
        !Array.isArray(value.segments) || value.segments.length > MAX_SEGMENTS) {
      reject("Nieobsługiwany lub uszkodzony eksport transkrypcji Video Notes.");
    }
    var seen = new Set();
    var previousStart = -1;
    var segments = [];
    for (var original of value.segments) {
      if (!plainObject(original) || !validText(original.id, 60) ||
          !/^[A-Za-z0-9_-]{1,60}$/.test(original.id) ||
          seen.has(original.id) || !validTime(original.start_ms) ||
          !validTime(original.end_ms) || original.end_ms <= original.start_ms ||
          original.start_ms < previousStart || !validText(original.text, MAX_TEXT)) {
        reject("Eksport zawiera niepoprawny lub zduplikowany segment.");
      }
      seen.add(original.id);
      previousStart = original.start_ms;
      segments.push({
        id: original.id, start_ms: original.start_ms,
        end_ms: original.end_ms, text: original.text
      });
    }
    return {
      schema: SCHEMA, project_id: value.project_id, language: value.language,
      complete: value.complete, segments: segments
    };
  }
  function parseExport(source) {
    if (!validText(source, MAX_BYTES)) reject("Plik jest zbyt duży lub nie zawiera poprawnego tekstu.");
    var parsed;
    try { parsed = JSON.parse(source); }
    catch (_error) { reject("Plik nie jest poprawnym JSON."); }
    return validateExport(parsed);
  }
  function clock(ms, vtt) {
    if (!validTime(ms)) reject("Nieprawidłowy znacznik czasu.");
    var hours = Math.floor(ms / 3600000);
    var minutes = Math.floor(ms % 3600000 / 60000);
    var seconds = Math.floor(ms % 60000 / 1000);
    var milli = ms % 1000;
    var pad = function (n, digits) { return String(n).padStart(digits, "0"); };
    return pad(hours, 2) + ":" + pad(minutes, 2) + ":" +
      pad(seconds, 2) + (vtt ? "." : ",") + pad(milli, 3);
  }
  function corrected(model, edits) {
    var doc = validateExport(model);
    if (!plainObject(edits)) reject("Nieprawidłowa lista poprawek.");
    var ids = new Set(doc.segments.map(function (s) { return s.id; }));
    for (var key of Object.keys(edits)) {
      if (!ids.has(key) || !validText(edits[key], MAX_TEXT)) {
        reject("Poprawka odnosi się do nieznanego segmentu albo jest za długa.");
      }
    }
    return {
      schema: SCHEMA, project_id: doc.project_id, language: doc.language,
      complete: doc.complete,
      segments: doc.segments.map(function (item) {
        return {
          id: item.id, start_ms: item.start_ms, end_ms: item.end_ms,
          text: Object.prototype.hasOwnProperty.call(edits, item.id) ?
            edits[item.id] : item.text
        };
      }).filter(function (item) { return Boolean(item.text.trim()); })
    };
  }
  // Keep one segment in one subtitle cue, while TXT and JSON remain verbatim.
  function cueText(value, vtt) {
    var line = value.replace(/[\r\n\v\f\u001c-\u001e\u0085\u2028\u2029]+/g, " ").trim();
    return vtt ? line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") : line;
  }
  // Build only the requested format; avoid allocating three extra large files per download.
  function renderExport(model, edits, filename) {
    var doc = corrected(model, edits || Object.create(null));
    checkBudget(doc, edits || Object.create(null), false);
    if (filename === "transcript.txt") {
      return utf8BytesUnderLimit(doc.segments.map(function (s) { return s.text; }).join("\n") +
        (doc.segments.length ? "\n" : ""));
    }
    if (filename === "transcript.srt") {
      var srt = doc.segments.map(function (s, i) {
        return String(i + 1) + "\n" + clock(s.start_ms, false) + " --> " +
          clock(s.end_ms, false) + "\n" + cueText(s.text, false);
      }).join("\n\n");
      return utf8BytesUnderLimit(srt + (srt ? "\n" : ""));
    }
    if (filename === "transcript.vtt") {
      var vtt = doc.segments.map(function (s) {
        return clock(s.start_ms, true) + " --> " + clock(s.end_ms, true) +
          "\n" + cueText(s.text, true);
      }).join("\n\n");
      return utf8BytesUnderLimit("WEBVTT\n\n" + vtt + (doc.segments.length ? "\n" : ""));
    }
    if (filename === "transcript.json") return utf8BytesUnderLimit(JSON.stringify(doc, null, 2) + "\n");
    reject("Nieobsługiwany format eksportu.");
  }
  // Preserve compatibility for existing programmatic callers.
  function renderExports(model, edits) {
    var files = {};
    ["transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json"].forEach(function (name) {
      files[name] = renderExport(model, edits, name);
    });
    return files;
  }
  // A reversible patch for a matching desktop project, not a replacement ASR transcript.
  function renderCorrections(model, edits) {
    var doc = validateExport(model);
    var map = edits || Object.create(null);
    if (!plainObject(map)) reject("Nieprawidłowa lista poprawek.");
    var byId = new Map(doc.segments.map(function (item) { return [item.id, item]; }));
    for (var key of Object.keys(map)) {
      if (!byId.has(key) || !validText(map[key], MAX_TEXT)) {
        reject("Poprawka odnosi się do nieznanego segmentu albo jest za długa.");
      }
    }
    checkBudget(doc, map, true);
    var changes = [];
    doc.segments.forEach(function (item) {
      if (Object.prototype.hasOwnProperty.call(map, item.id) && map[item.id] !== item.text) {
        changes.push({
          id: item.id, start_ms: item.start_ms, end_ms: item.end_ms,
          before: item.text, after: map[item.id]
        });
      }
    });
    return utf8BytesUnderLimit(JSON.stringify({schema: "videonotes-web-corrections-v1",
      project_id: doc.project_id, changes: changes}, null, 2) + String.fromCharCode(10), MAX_PATCH_BYTES);
  }
  // Reapply an explicitly saved browser patch only to the exact source.
  // No partial changes, cloud calls or persistent storage.
  function parseCorrections(model, source) {
    var doc = validateExport(model);
    if (typeof source !== "string" || source.length > MAX_PATCH_BYTES) {
      reject("Plik poprawek przekracza limit 20 MiB lub nie jest poprawnym tekstem.");
    }
    var patch;
    try { patch = JSON.parse(source); }
    catch (_error) { reject("Plik poprawek nie jest poprawnym JSON."); }
    if (!plainObject(patch) ||
        Object.keys(patch).sort().join(",") !== "changes,project_id,schema" ||
        patch.schema !== "videonotes-web-corrections-v1" ||
        patch.project_id !== doc.project_id ||
        !Array.isArray(patch.changes) || patch.changes.length > MAX_SEGMENTS) {
      reject("Paczka nie pasuje do transkrypcji lub ma niepoprawny format.");
    }
    var byId = new Map(doc.segments.map(function (item) { return [item.id, item]; }));
    var seen = new Set();
    var result = Object.create(null);
    for (var row of patch.changes) {
      if (!plainObject(row) ||
          Object.keys(row).sort().join(",") !== "after,before,end_ms,id,start_ms" ||
          typeof row.id !== "string" || !/^[A-Za-z0-9_-]{1,60}$/.test(row.id) ||
          seen.has(row.id) || !byId.has(row.id) ||
          !validText(row.before, MAX_TEXT) || !validText(row.after, MAX_TEXT)) {
        reject("Paczka zawiera obcą, zduplikowaną lub nieprawidłową poprawkę.");
      }
      var base = byId.get(row.id);
      if (row.start_ms !== base.start_ms || row.end_ms !== base.end_ms ||
          row.before !== base.text) {
        reject("Tekst lub czasy źródłowe zmieniły się; nie zastosowano żadnej poprawki.");
      }
      seen.add(row.id);
      if (row.after !== row.before) result[row.id] = row.after;
    }
    return result;
  }
  function search(model, edits, term) {
    var doc = validateExport(model);
    var query = String(term || "").trim().toLocaleLowerCase();
    var results = [];
    doc.segments.forEach(function (s, index) {
      var edited = edits && Object.prototype.hasOwnProperty.call(edits, s.id) ?
        edits[s.id] : s.text;
      if (!query || String(edited).toLocaleLowerCase().includes(query) ||
          s.id.toLowerCase().includes(query)) {
        results.push(index);
      }
    });
    return results;
  }
  var core = {
    SCHEMA: SCHEMA, MAX_BYTES: MAX_BYTES, MAX_TEXT: MAX_TEXT, MAX_OUTPUT_BYTES: MAX_OUTPUT_BYTES, MAX_PATCH_BYTES: MAX_PATCH_BYTES,
    parseExport: parseExport, validateExport: validateExport,
    clock: clock, corrected: corrected, renderExport: renderExport,
    renderExports: renderExports, renderCorrections: renderCorrections,
    parseCorrections: parseCorrections,
    search: search
  };
  if (typeof module !== "undefined" && module.exports) module.exports = core;
  root.VideoNotesWebCore = core;
})(typeof globalThis !== "undefined" ? globalThis : this);
