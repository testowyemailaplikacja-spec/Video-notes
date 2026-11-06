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
  function renderExports(model, edits) {
    var doc = corrected(model, edits || {});
    var srt = doc.segments.map(function (s, i) {
      return String(i + 1) + "\n" + clock(s.start_ms, false) + " --> " +
        clock(s.end_ms, false) + "\n" + s.text;
    }).join("\n\n");
    var vtt = "WEBVTT\n\n" + doc.segments.map(function (s) {
      return clock(s.start_ms, true) + " --> " + clock(s.end_ms, true) +
        "\n" + s.text;
    }).join("\n\n");
    return {
      "transcript.txt": doc.segments.map(function (s) { return s.text; }).join("\n") +
        (doc.segments.length ? "\n" : ""),
      "transcript.srt": srt + (srt ? "\n" : ""),
      "transcript.vtt": vtt + (doc.segments.length ? "\n" : ""),
      "transcript.json": JSON.stringify(doc, null, 2) + "\n"
    };
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
    SCHEMA: SCHEMA, MAX_BYTES: MAX_BYTES, MAX_TEXT: MAX_TEXT,
    parseExport: parseExport, validateExport: validateExport,
    clock: clock, corrected: corrected, renderExports: renderExports,
    search: search
  };
  if (typeof module !== "undefined" && module.exports) module.exports = core;
  root.VideoNotesWebCore = core;
})(typeof globalThis !== "undefined" ? globalThis : this);
