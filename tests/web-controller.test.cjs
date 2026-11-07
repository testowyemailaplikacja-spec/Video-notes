"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const core = require("../web/transcript-core.js");

function source(name, count) {
  return {
    schema: core.SCHEMA, project_id: name, language: "pl", complete: true,
    segments: Array.from({length: count}, (_, i) => ({
      id: "seg-" + i, start_ms: i * 1500,
      end_ms: i * 1500 + 1000, text: name + " text " + i
    }))
  };
}

class Element {
  constructor() {
    this.events = Object.create(null);
    this.children = [];
    this.value = "";
    this.textContent = "";
    this.disabled = true;
    this.classList = {toggle() {}};
  }
  addEventListener(type, handler) { this.events[type] = handler; }
  replaceChildren(...nodes) { this.children = nodes; }
  appendChild(node) { this.children.push(node); }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(key, value) { this[key] = value; }
}

function boot() {
  const elements = Object.create(null);
  const state = {allow: false, prompts: []};
  const win = {
    VideoNotesWebCore: core,
    events: Object.create(null),
    addEventListener(name, handler) { this.events[name] = handler; },
    confirm(message) { state.prompts.push(message); return state.allow; }
  };
  const doc = {
    getElementById(id) { return elements[id] ||= new Element(); },
    createElement() { return new Element(); },
    querySelectorAll() { return []; }
  };
  const code = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
  vm.runInNewContext(code, {window: win, document: doc}, {filename: "web/app.js"});
  async function importFile(data, read = async () => JSON.stringify(data)) {
    return elements["source-file"].events.change({
      target: {files: [{size: 1024, name: data.project_id, text: read}]}
    });
  }
  function select(index) {
    const row = elements["segment-rows"].children[index];
    row.children[1].children[0].events.click();
  }
  return {elements, state, win, importFile, select};
}

function unload(ux) {
  const event = {prevented: false, preventDefault() { this.prevented = true; }};
  ux.win.events.beforeunload(event);
  return event;
}

test("pending textarea changes are protected when selecting a different segment", async () => {
  const ux = boot();
  await ux.importFile(source("original", 2));
  assert.equal(unload(ux).prevented, false);
  ux.select(0);
  ux.elements["edit-text"].value = "Uncommitted editor value";
  ux.select(1);
  assert.match(ux.elements["selected-label"].textContent, /Segment seg-0/);
  assert.equal(ux.elements["edit-text"].value, "Uncommitted editor value");
  assert.equal(ux.state.prompts.length, 1);
  const before = unload(ux);
  assert.equal(before.prevented, true);
  assert.equal(before.returnValue, "");
  ux.state.allow = true;
  ux.select(1);
  assert.match(ux.elements["selected-label"].textContent, /Segment seg-1/);
});

test("saved in-memory corrections block replacement until explicit confirmation", async () => {
  const ux = boot();
  await ux.importFile(source("original", 2));
  ux.select(0);
  ux.elements["edit-text"].value = "Corrected";
  ux.elements["save-edit"].events.click();
  assert.match(ux.elements["edit-count"].textContent, /1 poprawek/);
  assert.equal(unload(ux).prevented, true);
  ux.state.allow = false;
  await ux.importFile(source("new-file", 1));
  assert.match(ux.elements["match-count"].textContent, /^2 z 2/);
  assert.match(ux.elements["edit-text"].value, /Corrected/);
  ux.state.allow = true;
  await ux.importFile(source("new-file", 1));
  assert.match(ux.elements["match-count"].textContent, /^1 z 1/);
  assert.match(ux.elements["edit-count"].textContent, /^0 poprawek/);
  assert.equal(unload(ux).prevented, false);
});

test("slow older file read may not replace newer successfully imported file", async () => {
  const ux = boot();
  let resolveOld;
  const old = ux.importFile(source("old", 2), () => new Promise(resolve => {resolveOld = resolve;}));
  await ux.importFile(source("latest", 1));
  assert.match(ux.elements["match-count"].textContent, /^1 z 1/);
  resolveOld(JSON.stringify(source("old", 2)));
  await old;
  assert.match(ux.elements["match-count"].textContent, /^1 z 1/);
  ux.select(0);
  assert.equal(ux.elements["edit-text"].value, "latest text 0");
});

test("reset restores imported segment and removes saved in-memory correction", async () => {
  const ux = boot();
  await ux.importFile(source("original", 2));
  ux.select(0);
  ux.elements["edit-text"].value = "Manual correction";
  ux.elements["save-edit"].events.click();
  assert.equal(unload(ux).prevented, true);
  ux.elements["reset-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "original text 0");
  assert.match(ux.elements["edit-count"].textContent, /^0 poprawek/);
  assert.equal(unload(ux).prevented, false);
});

test("reset never silently discards unsaved textarea text", async () => {
  const ux = boot();
  await ux.importFile(source("original", 2));
  ux.select(0);
  ux.elements["edit-text"].value = "Still editing";
  ux.elements["reset-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "Still editing");
  assert.equal(ux.state.prompts.length, 1);
  ux.state.allow = true;
  ux.elements["reset-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "original text 0");
  assert.equal(unload(ux).prevented, false);
});
