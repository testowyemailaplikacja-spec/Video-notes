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

test("browser JSON parser rejects duplicate root and nested keys, including unicode aliases", () => {
  const doc = JSON.stringify(fixture());
  const duplicateSchema = doc.replace(
    '"schema":"videonotes-export-v1"',
    '"schema":"videonotes-export-v1","schema":"videonotes-export-v1"'
  );
  assert.throws(() => core.parseExport(duplicateSchema), /Zduplikowany klucz JSON/);
  const duplicateText = doc.replace(
    '"text":"Dzień dobry, witam na wykładzie."',
    '"text":"A suspicious edit","text":"Dzień dobry, witam na wykładzie."'
  );
  assert.throws(() => core.parseExport(duplicateText), /Zduplikowany klucz JSON/);
  const escapedAlias = doc.replace(
    '"text":"Dzień dobry, witam na wykładzie."',
    '"\\u0074ext":"Injected","text":"Dzień dobry, witam na wykładzie."'
  );
  assert.throws(() => core.parseExport(escapedAlias), /Zduplikowany klucz JSON/);
  const colonAndBraces = fixture();
  colonAndBraces.segments[0].text = 'Literal text: {"after":"not a property"}, \\';
  assert.equal(core.parseExport(JSON.stringify(colonAndBraces)).segments[0].text,
               colonAndBraces.segments[0].text);
});

test("UTF-8 BOM is accepted for exported transcript and correction patches", () => {
  const base = fixture();
  assert.deepEqual(core.parseExport(String.fromCharCode(0xFEFF) + JSON.stringify(base)), base);
  const changes = Object.create(null);
  changes[base.segments[0].id] = "Corrected";
  const patch = core.renderCorrections(base, changes);
  assert.deepEqual(
    {...core.parseCorrections(base, String.fromCharCode(0xFEFF) + patch)},
    {...changes}
  );
  assert.throws(() => core.parseExport(String.fromCharCode(0xFEFF) +
    '{"schema":"videonotes-export-v1","schema":"other"}'), /Zduplikowany/);
});

test("browser patch import refuses duplicate edit after fields before applying any changes", () => {
  const doc = fixture();
  const edited = Object.create(null);
  edited[doc.segments[0].id] = "Nowa własna poprawka";
  const patch = core.renderCorrections(doc, edited);
  const field = /"after"\s*:\s*"Nowa własna poprawka"/;
  assert.match(patch, field, 'fixture must actually contain the target key');
  const bad = patch.replace(field,
                            '"after":"Injected", "after":"Nowa własna poprawka"');
  assert.notEqual(bad, patch);
  assert.throws(() => core.parseCorrections(doc, bad), /Zduplikowany klucz JSON/);
  const escaped = patch.replace(field,
                                '"\\u0061fter":"Injected", "after":"Nowa własna poprawka"');
  assert.notEqual(escaped, patch);
  assert.throws(() => core.parseCorrections(doc, escaped), /Zduplikowany klucz JSON/);
  assert.equal(core.parseCorrections(doc, patch)[doc.segments[0].id], edited[doc.segments[0].id]);
});

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

test("single-format export matches legacy all-format adapter", () => {
  const doc = fixture();
  const edits = Object.create(null);
  edits["c0000000-s00001"] = "Poprawka użytkownika.";
  const legacy = core.renderExports(doc, edits);
  for (const name of Object.keys(legacy)) {
    assert.equal(core.renderExport(doc, edits, name), legacy[name]);
  }
  assert.throws(() => core.renderExport(doc, edits, "transcript.html"), /Nieobsługiwany/);
  assert.equal(JSON.parse(core.renderExport(doc, edits, "transcript.json")).segments[1].text, edits["c0000000-s00001"]);
  assert.equal(doc.segments[1].text, "Protokół DHCP nadaje adres IP.");
});

test("subtitle exports flatten injected cue separators and escape WebVTT markup", () => {
  const doc = fixture();
  const edits = Object.create(null);
  const original = "Pierwszy wiersz\n\n00:01:00,000 --> 00:02:00,000\n<v Jan> A & B";
  edits["c0000000-s00000"] = original;
  const srt = core.renderExport(doc, edits, "transcript.srt");
  const vtt = core.renderExport(doc, edits, "transcript.vtt");
  assert.equal(srt.split("\n\n").length, doc.segments.length);
  assert.match(srt, /Pierwszy wiersz 00:01:00,000 --> 00:02:00,000 <v Jan> A & B/);
  assert.doesNotMatch(vtt, /<v Jan>/);
  assert.match(vtt, /&lt;v Jan&gt; A &amp; B/);
  assert.equal(JSON.parse(core.renderExport(doc, edits, "transcript.json")).segments[0].text, original);
  assert.ok(core.renderExport(doc, edits, "transcript.txt").includes(original));
});

test("offline browser correction patch round-trips without exporting unchanged text", () => {
  const doc = fixture();
  const edits = Object.create(null);
  edits["c0000000-s00001"] = "Poprawione DHCP i IPv6";
  edits["c0000000-s00000"] = "";
  const patch = JSON.parse(core.renderCorrections(doc, edits));
  assert.equal(patch.schema, "videonotes-web-corrections-v1");
  assert.equal(patch.project_id, doc.project_id);
  assert.deepEqual(patch.changes.map(item => item.id), ["c0000000-s00000", "c0000000-s00001"]);
  assert.equal(patch.changes[0].before, doc.segments[0].text);
  assert.equal(patch.changes[0].after, "");
  assert.equal(patch.changes[1].after, "Poprawione DHCP i IPv6");
  assert.equal(doc.segments[1].text, "Protokół DHCP nadaje adres IP.");
  assert.equal(JSON.parse(core.renderCorrections(doc, {})).changes.length, 0);
  assert.throws(() => core.renderCorrections(doc, {"unknown-segment": "a"}), /Poprawka/);
  assert.throws(() => core.renderCorrections(doc, {"c0000000-s00001": "\u0000"}), /Poprawka/);
});

test("all export formats and web correction patches enforce a bounded output budget without changing source", () => {
  const source = fixture();
  const original = JSON.stringify(source);
  const huge = "a".repeat(9999);
  const doc = {
    schema: core.SCHEMA, project_id: "large-local-only", language: "pl", complete: true,
    segments: Array.from({length: 7200}, (_, i) => ({
      id: "seg-" + i, start_ms: i * 1000, end_ms: i * 1000 + 900, text: "Test"
    }))
  };
  const edits = Object.create(null);
  for (const item of doc.segments) edits[item.id] = huge;
  assert.throws(() => core.renderExport(doc, edits, "transcript.txt"), /64 MiB/);
  assert.throws(() => core.renderExport(doc, edits, "transcript.json"), /64 MiB/);
  assert.throws(() => core.renderCorrections(doc, edits), /20 MiB/);
  assert.equal(JSON.stringify(source), original);
  assert.equal(doc.segments[0].text, "Test");
  const standard = core.renderExports(source, {"c0000000-s00000": "Zażółć gęślą jaźń"});
  assert.match(standard["transcript.txt"], /Zażółć gęślą jaźń/);
});

test("non-ASCII byte count and subtitle escaping cannot circumvent output cap", () => {
  const doc = {
    schema: core.SCHEMA, project_id: "non-ascii", language: "pl", complete: true,
    segments: Array.from({length: 4200}, (_, i) => ({
      id: "seg-" + i, start_ms: i * 1000, end_ms: i * 1000 + 900, text: "ź".repeat(8999)
    }))
  };
  assert.throws(() => core.renderExport(doc, {}, "transcript.txt"), /64 MiB/);
  assert.throws(() => core.renderExport(doc, {}, "transcript.vtt"), /64 MiB/);
  assert.equal(doc.segments[0].text.length, 8999);
});

test("browser correction patch never exceeds desktop import's 20 MiB limit", () => {
  assert.equal(core.MAX_PATCH_BYTES, 20 * 1024 * 1024);
  const raw = {schema: core.SCHEMA, project_id: "patch-import", language: "pl", complete: true,
    segments: Array.from({length: 3100}, (_, i) => ({
      id: "c-" + i, start_ms: i * 1000, end_ms: i * 1000 + 900, text: "source"
    }))
  };
  const changed = Object.create(null);
  const longEdit = "a".repeat(7500);
  for (const row of raw.segments) changed[row.id] = longEdit;
  assert.throws(() => core.renderCorrections(raw, changed), /20 MiB/);
  assert.equal(raw.segments[0].text, "source");
  const small = Object.create(null); small["c-0"] = "Bezpieczna korekta";
  assert.equal(JSON.parse(core.renderCorrections(raw, small)).changes.length, 1);
});

test("saved patch reimport restores unicode corrections only to exact source", () => {
  const doc = fixture();
  const changes = {"c0000000-s00000": "Zażółć gęślą jaźń", "c0000000-s00001": ""};
  const saved = core.renderCorrections(doc, changes);
  const imported = core.parseCorrections(doc, saved);
  assert.equal(Object.getPrototypeOf(imported), null);
  assert.equal(imported["c0000000-s00000"], changes["c0000000-s00000"]);
  assert.equal(imported["c0000000-s00001"], "");
  assert.equal(doc.segments[0].text, "Dzień dobry, witam na wykładzie.");
  assert.throws(() => core.parseCorrections({...doc,project_id:"other"},saved), /nie pasuje/);
  const tampered = fixture(); tampered.segments[0].text = "Obca treść";
  assert.throws(() => core.parseCorrections(tampered,saved), /źródłowe/);
  const reTimed = fixture(); reTimed.segments[0].start_ms = 1;
  assert.throws(() => core.parseCorrections(reTimed,saved), /źródłowe/);
});
test("patch import rejects duplicate IDs, foreign fields, nulls and malicious strings", () => {
  const doc = fixture();
  const safe=JSON.parse(core.renderCorrections(doc,{"c0000000-s00000":"Korekta"}));
  const read = obj => core.parseCorrections(doc,JSON.stringify(obj));
  assert.throws(() => core.parseCorrections(doc,"{broken"),/JSON/);
  assert.throws(() => core.parseCorrections(doc,"x".repeat(core.MAX_PATCH_BYTES+1)),/20 MiB/);
  assert.throws(() => read({...safe,secret:"bad"}),/format/);
  assert.throws(() => read({...safe,changes:[safe.changes[0],safe.changes[0]]}),/zduplikowaną/);
  assert.throws(() => read({...safe,changes:[{...safe.changes[0],id:"alien"}]}),/obcą/);
  assert.throws(() => read({...safe,changes:[{...safe.changes[0],before:"forged"}]}),/źródłowe/);
  assert.throws(() => read({...safe,changes:[{...safe.changes[0],unexpected:"x"}]}),/nieprawidłową/);
  assert.throws(() => read({...safe,changes:[{...safe.changes[0],after:"bad\u0000"}]}),/nieprawidłową/);
  assert.equal(Object.keys(read({...safe,changes:[]})).length,0);
});

test("binary timestamp lookup handles start, gaps, overlaps and equal starts", () => {
  const rows = [
    {start_ms: 1000, end_ms: 3000},
    {start_ms: 2000, end_ms: 2800},
    {start_ms: 2000, end_ms: 4000},
    {start_ms: 7000, end_ms: 9000}
  ];
  assert.equal(core.locateAtTime(rows, 0), 0);
  assert.equal(core.locateAtTime(rows, 1999), 0);
  assert.equal(core.locateAtTime(rows, 2000), 2);
  assert.equal(core.locateAtTime(rows, 6999), 2);
  assert.equal(core.locateAtTime(rows, 7000), 3);
  assert.equal(core.locateAtTime(rows, 9000), 3);
  assert.throws(() => core.locateAtTime([], 1000), /pusta transkrypcja/);
  assert.throws(() => core.locateAtTime(rows, NaN), /Nieprawidłowy czas/);
  assert.throws(() => core.locateAtTime(rows, -1), /Nieprawidłowy czas/);
});
test("timestamp lookup supports 50k items without scanning the entire source", () => {
  const rows = Array.from({length: 50000}, (_, i) => ({start_ms: i * 1500, end_ms: i * 1500 + 1000}));
  for (let i = 0; i < 50000; i += 97) {
    assert.equal(core.locateAtTime(rows, i * 1500), i);
    assert.equal(core.locateAtTime(rows, i * 1500 + 1100), i);
  }
  assert.equal(core.locateAtTime(rows, 49999 * 1500), 49999);
});
