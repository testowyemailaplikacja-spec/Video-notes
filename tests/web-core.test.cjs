"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("../web/transcript-core.js");

function fixture() {
  return {
    schema: "videonotes-export-v1",
    project_id: "project-123", language: "pl", complete: true,
    segments: [
      {id: "c0000000-s00000", start_ms: 0, end_ms: 1500, text: "Dzień dobry, witam na wykładzie."},
      {id: "c0000000-s00001", start_ms: 1600, end_ms: 19000, text: "Protokół DHCP nadaje adres IP."},
      {id: "c0000001-s00000", start_ms: 60000, end_ms: 76500, text: "Pytanie na koniec?"}
    ]
  };
}

test("parse validates schema and returns independent source copy", () => {
  const raw = fixture();
  const parsed = core.parseExport(JSON.stringify(raw));
  assert.deepEqual(parsed, raw);
  parsed.segments[0].text = "Edited in memory";
  assert.equal(raw.segments[0].text, "Dzień dobry, witam na wykładzie.");
  assert.deepEqual(core.search(raw, Object.create(null), "DHCP"), [1]);
  assert.equal(core.clock(61234, true), "00:01:01.234");
  assert.equal(core.clock(61234, false), "00:01:01,234");
});

test("exports corrected text while leaving original untouched", () => {
  const raw = fixture();
  const edits = Object.create(null);
  edits["c0000000-s00001"] = "Ręcznie poprawiony protokół DHCP i IPv4.";
  const files = core.renderExports(raw, edits);
  assert.match(files["transcript.txt"], /Ręcznie poprawiony/);
  assert.match(files["transcript.srt"], /00:00:01,600 --> 00:00:19,000/);
  assert.match(files["transcript.vtt"], /^WEBVTT\n\n/);
  assert.match(files["transcript.vtt"], /00:00:01\.600/);
  const json = JSON.parse(files["transcript.json"]);
  assert.equal(json.segments[1].text, edits["c0000000-s00001"]);
  assert.equal(raw.segments[1].text, "Protokół DHCP nadaje adres IP.");
  assert.deepEqual(core.search(raw, edits, "IPv4"), [1]);
});

test("empty correction removes exported cue, not raw source", () => {
  const doc = fixture();
  const edits = Object.create(null);
  edits["c0000000-s00000"] = "";
  const out = core.renderExports(doc, edits);
  assert.equal(JSON.parse(out["transcript.json"]).segments.length, 2);
  assert.equal(doc.segments.length, 3);
  assert.match(out["transcript.srt"], /^1\n00:00:01,600/);
});

test("untrusted HTML remains literal and no HTML rendering is performed by core", () => {
  const doc = fixture();
  const edits = Object.create(null);
  edits["c0000000-s00001"] = "<img src=x onerror=alert(1)>\n[link](https://example.invalid)";
  const out = core.renderExports(doc, edits);
  assert.match(out["transcript.txt"], /<img src=x onerror=alert\(1\)>/);
  assert.match(out["transcript.json"], /example.invalid/);
  assert.deepEqual(core.search(doc, edits, "onerror"), [1]);
});

test("reject duplicate ids, reversed times, invalid fields and oversized data", () => {
  const first = fixture();
  first.segments[1].id = first.segments[0].id;
  assert.throws(() => core.validateExport(first), /segment/);
  const reverse = fixture();
  reverse.segments[1].start_ms = 20000;
  reverse.segments[1].end_ms = 10000;
  assert.throws(() => core.validateExport(reverse), /segment/);
  const order = fixture();
  order.segments[2].start_ms = 1000;
  assert.throws(() => core.validateExport(order), /segment/);
  const bad = fixture();
  bad.language = "fr";
  assert.throws(() => core.validateExport(bad), /eksport/);
  assert.throws(() => core.parseExport("{broken-json"), /JSON/);
  assert.throws(() => core.parseExport("x".repeat(core.MAX_BYTES + 1)), /duży/);
  assert.throws(() => core.renderExports(fixture(), {"unknown-id": "foo"}), /Poprawka/);
  assert.throws(() => core.renderExports(fixture(), {"c0000000-s00000": "\u0000"}), /Poprawka/);
});

test("prototype-less correction handles special IDs safely", () => {
  const doc = fixture();
  doc.segments[0].id = "__proto__";
  const edits = Object.create(null);
  edits["__proto__"] = "Naprawiona wypowiedź.";
  const out = core.renderExports(doc, edits);
  assert.equal(JSON.parse(out["transcript.json"]).segments[0].text, "Naprawiona wypowiedź.");
  assert.equal(Object.prototype.polluted, undefined);
});
