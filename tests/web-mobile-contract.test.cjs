"use strict";
/* Desktop/mobile/browser v1 contract parity using synthetic input only.
 * No network calls, media files, models, devices or production apps are used.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const {spawnSync} = require("node:child_process");
const path = require("node:path");
const core = require("../web/transcript-core.js");

const PYTHON = `import json,sys
from videonotes.mobile_contract import parse_portable_export
try:
    value = parse_portable_export(sys.stdin.buffer.read())
except Exception:
    sys.exit(2)
sys.stdout.write(json.dumps(value, ensure_ascii=True, sort_keys=True))
`;

function pythonParse(raw) {
  return spawnSync("python", ["-c", PYTHON], {
    cwd: path.resolve(__dirname, ".."), input: Buffer.from(raw, "utf8"),
    encoding: "utf8", timeout: 15000, maxBuffer: 2 * 1024 * 1024
  });
}

function documentFixture() {
  return {
    schema: "videonotes-export-v1",
    project_id: "local-PL-01", language: "auto", complete: false,
    segments: [
      {id: "c0000000-s00000", start_ms: 0, end_ms: 1500,
       text: "Zażółć gęślą jaźń! DHCP/IPv6. { \"text\": \"source\" }"},
      {id: "c0000000-s00001", start_ms: 1600, end_ms: 3500,
       text: "Zażółć gęślą jaźń! DHCP/IPv6. { \"text\": \"source\" }"}
    ]
  };
}

test("Python mobile and offline browser accept identical v1 transcript", () => {
  const model = documentFixture();
  const raw = JSON.stringify({...model, extra_ignored_field: true});
  const browser = core.parseExport(raw);
  const result = pythonParse(raw);
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stderr);
  const python = JSON.parse(result.stdout);
  assert.deepEqual(python, browser);
  assert.deepEqual(browser, model);
  assert.equal(browser.segments.length, 2, "repeated speech must be retained");
});

test("desktop, mobile and browser reject the same malformed source fields", () => {
  const bad = [];
  const base = documentFixture();
  const push = mutate => {
    const copy = JSON.parse(JSON.stringify(base));
    mutate(copy);
    bad.push(JSON.stringify(copy));
  };
  push(doc => { doc.segments[1].id = doc.segments[0].id; });
  push(doc => { doc.segments[1].start_ms = 0; doc.segments[1].end_ms = 0; });
  push(doc => { doc.complete = "yes"; });
  push(doc => { doc.language = []; });
  push(doc => { doc.language = {}; });
  push(doc => { doc.segments[1].start_ms = true; });
  push(doc => { doc.segments[0].text = "😀".repeat(5001); });
  push(doc => { doc.segments[1].id = "../bad"; });
  bad.push('{"schema":"videonotes-export-v1","schema":"fake","project_id":"x","language":"pl","complete":true,"segments":[]}');
  bad.push('{"schema":"videonotes-export-v1","project_id":"x","language":"pl","complete":true,"segments":[{"id":"x","start_ms":0,"end_ms":3,"text":"ok","text":"fake"}]}');
  for (const [i, raw] of bad.entries()) {
    assert.throws(() => core.parseExport(raw), undefined, "Browser accepted invalid fixture " + i);
    const result = pythonParse(raw);
    assert.equal(result.status, 2, "Python accepted invalid fixture " + i);
  }
});

test("BOM-prefixed local UTF-8 export has identical Python and browser meaning", () => {
  const raw = String.fromCharCode(0xFEFF) + JSON.stringify(documentFixture());
  const browser = core.parseExport(raw);
  const python = pythonParse(raw);
  assert.equal(python.status, 0, python.stderr);
  assert.deepEqual(JSON.parse(python.stdout), browser);
});

test("both parsers accept extra metadata but strip it from canonical result", () => {
  const model = documentFixture();
  model.segments[0].debug = "PRIVATE_UNUSED";
  model.untrusted = {runtime: "not a schema field"};
  const raw = JSON.stringify(model);
  const browser = core.parseExport(raw);
  const result = pythonParse(raw);
  assert.equal(result.status, 0, result.stderr);
  const mobile = JSON.parse(result.stdout);
  assert.deepEqual(mobile, browser);
  assert.equal(Object.hasOwn(browser, "untrusted"), false);
  assert.equal(Object.hasOwn(browser.segments[0], "debug"), false);
});


const PYTHON_CORRECTIONS = [
  "import json,sys",
  "from videonotes.mobile_corrections import render_mobile_corrections, parse_mobile_corrections",
  "value=json.load(sys.stdin)",
  "try:",
  "    if value['mode']=='render':",
  "        out=render_mobile_corrections(value['document'],value['edits'])",
  "        print(out.decode('utf-8'))",
  "    else:",
  "        patch=parse_mobile_corrections(value['document'],value['raw'].encode('utf-8'))",
  "        print(json.dumps(patch,ensure_ascii=False))",
  "except Exception:",
  "    sys.exit(2)",
].join("\n");

function pythonCorrections(payload) {
  return spawnSync("python", ["-c", PYTHON_CORRECTIONS], {
    cwd: path.resolve(__dirname, ".."), input: JSON.stringify(payload),
    encoding: "utf8", timeout: 15000, maxBuffer: 4 * 1024 * 1024
  });
}

test("Mobile Python corrections are accepted by offline browser without source loss", () => {
  const original = documentFixture();
  const untouched = JSON.stringify(original);
  const edits = {"c0000000-s00001": "Poprawka: DHCP i zażółć 😀"};
  const python = pythonCorrections({mode: "render", document: original, edits});
  assert.equal(python.status, 0, python.stderr);
  const imported = core.parseCorrections(original, python.stdout.trim());
  assert.equal(Object.getPrototypeOf(imported), null);
  assert.deepEqual({...imported}, edits);
  assert.equal(JSON.stringify(original), untouched, "input source was mutated");
  const browserPatch = core.renderCorrections(original, edits);
  const parsed = pythonCorrections({mode: "parse", document: original, raw: browserPatch});
  assert.equal(parsed.status, 0, parsed.stderr);
  assert.deepEqual(JSON.parse(parsed.stdout), edits);
});

test("Mobile and browser corrections reject same-source mismatches and duplicate JSON keys", () => {
  const model = documentFixture();
  const raw = core.renderCorrections(model, {"c0000000-s00000": "Poprawiono"});
  const invalid = [
    raw.replace('"project_id": "local-PL-01"', '"project_id": "wrong"'),
    raw.replace('"start_ms": 0', '"start_ms": 19'),
    raw.replace('"before": "Zażółć', '"before": "Niepoparte Zażółć'),
    raw.replace('"after": "Poprawiono"', '"after": "Poprawiono", "after": "inne"'),
  ];
  for (const patch of invalid) {
    assert.notEqual(patch, raw, "fixture mutation failed");
    assert.throws(() => core.parseCorrections(model, patch));
    const py = pythonCorrections({mode: "parse", document: model, raw: patch});
    assert.equal(py.status, 2, py.stderr);
  }
});
