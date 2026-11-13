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
