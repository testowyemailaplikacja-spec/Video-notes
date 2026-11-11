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
  removeAttribute(key) { delete this[key]; }
  pause() { this.pauseCount = (this.pauseCount || 0) + 1; }
  load() { this.loadCount = (this.loadCount || 0) + 1; }
}

function boot() {
  const elements = Object.create(null);
  const state = {allow: false, prompts: [], downloads: [], revoked: []};
  const exportButtons = ["transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json", "web-corrections.json"].map(name => {
    const button = new Element();
    button.getAttribute = key => key === "data-export" ? name : null;
    return button;
  });
  const win = {
    VideoNotesWebCore: core,
    events: Object.create(null),
    addEventListener(name, handler) { this.events[name] = handler; },
    confirm(message) { state.prompts.push(message); return state.allow; }
  };
  const doc = {
    activeElement: null,
    getElementById(id) { return elements[id] ||= new Element(); },
    createElement() {
      const node = new Element();
      node.focus = () => { doc.activeElement = node; };
      node.click = () => { state.downloads.push({filename: node.download, payload: state.payload}); };
      node.remove = () => {};
      return node;
    },
    querySelectorAll(selector) { return selector === "button[data-export]" ? exportButtons : []; },
    body: {appendChild() {} }
  };
  const code = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
  vm.runInNewContext(code, {window: win, document: doc,
    Blob: class { constructor(parts) {state.payload = parts.join("");} },
    URL: {createObjectURL: () => "blob:local", revokeObjectURL(url) { state.revoked.push(url); } },
    setTimeout: fn => fn()
  }, {filename: "web/app.js"});
  async function importFile(data, read = async () => JSON.stringify(data)) {
    return elements["source-file"].events.change({
      target: {files: [{size: 1024, name: data.project_id, text: read}]}
    });
  }
  async function importPatch(data, read = async () => JSON.stringify(data)) {
    return elements["corrections-file"].events.change({
      target: {files:[{size:1024,name:"web-corrections.json",text:read}]}
    });
  }
  function importMedia(size = 1024) {
    return elements["source-media"].events.change({
      target: {files:[{size, name:"synthetic.wav", type:"audio/wav"}]}
    });
  }
  function select(index) {
    const row = elements["segment-rows"].children[index];
    row.children[1].children[0].events.click();
  }
  return {elements, state, win, doc, importFile, importPatch, importMedia, select, exportButtons};
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

test("export refuses unsaved textarea draft and accepts explicitly saved changes", async () => {
  const ux = boot();
  await ux.importFile(source("original", 2));
  ux.select(0);
  ux.elements["edit-text"].value = "Uncommitted value";
  ux.elements["edit-text"].events.input();
  ux.exportButtons[0].events.click();
  assert.equal(ux.state.downloads.length, 0);
  assert.match(ux.elements["status"].textContent, /Najpierw kliknij/);
  assert.equal(ux.elements["edit-text"].value, "Uncommitted value");
  ux.elements["save-edit"].events.click();
  ux.exportButtons[0].events.click();
  assert.equal(ux.state.downloads.length, 1);
  assert.equal(ux.state.downloads[0].filename, "transcript.txt");
  assert.match(ux.state.downloads[0].payload, /Uncommitted value/);
});

test("changes made while an import is reading require fresh confirmation", async () => {
  const ux = boot();
  await ux.importFile(source("original", 2));
  let resolveNew;
  const pending = ux.importFile(source("second", 1), () => new Promise(resolve => {resolveNew = resolve;}));
  ux.select(0);
  ux.elements["edit-text"].value = "New draft while reading";
  ux.elements["edit-text"].events.input();
  resolveNew(JSON.stringify(source("second", 1)));
  await pending;
  assert.equal(ux.state.prompts.length, 1);
  assert.match(ux.state.prompts[0], /Podczas wczytywania/);
  assert.match(ux.elements["edit-text"].value, /New draft/);
  assert.match(ux.elements["match-count"].textContent, /^2 z 2/);
  assert.match(ux.elements["status"].textContent, /Import anulowany/);
  assert.equal(unload(ux).prevented, true);
});

test("a newly changed draft can also be explicitly discarded after file loading", async () => {
  const ux = boot();
  await ux.importFile(source("original", 2));
  ux.state.allow = true;
  let resolveNew;
  const pending = ux.importFile(source("second", 1), () => new Promise(resolve => {resolveNew = resolve;}));
  ux.select(0);
  ux.elements["edit-text"].value = "New draft while reading";
  ux.elements["edit-text"].events.input();
  resolveNew(JSON.stringify(source("second", 1)));
  await pending;
  assert.equal(ux.state.prompts.length, 1);
  assert.match(ux.elements["match-count"].textContent, /^1 z 1/);
  assert.equal(unload(ux).prevented, false);
});


test("segment selection exposes ARIA state and keeps focus after row redraw", async () => {
  const ux = boot();
  await ux.importFile(source("keyboard", 2));
  ux.select(0);
  const first = ux.elements["segment-rows"].children[0].children[1].children[0];
  const second = ux.elements["segment-rows"].children[1].children[1].children[0];
  assert.equal(first["aria-pressed"], "true");
  assert.equal(first["aria-controls"], "edit-text");
  assert.equal(second["aria-pressed"], "false");
  assert.equal(ux.doc.activeElement, first);
  ux.select(1);
  const selected = ux.elements["segment-rows"].children[1].children[1].children[0];
  assert.equal(selected["aria-pressed"], "true");
  assert.equal(ux.doc.activeElement, selected);
});

test("browser patch button exports only saved corrections and protects drafts", async () => {
  const ux = boot();
  await ux.importFile(source("desktop", 2));
  ux.exportButtons[4].events.click();
  assert.equal(ux.state.downloads.length, 0);
  assert.match(ux.elements["status"].textContent, /Brak zapisanych poprawek/);
  ux.select(1);
  ux.elements["edit-text"].value = "Nowa poprawka do desktopu";
  ux.exportButtons[4].events.click();
  assert.equal(ux.state.downloads.length, 0);
  ux.elements["save-edit"].events.click();
  ux.exportButtons[4].events.click();
  assert.equal(ux.state.downloads.length, 1);
  assert.equal(ux.state.downloads[0].filename, "web-corrections.json");
  const patch = JSON.parse(ux.state.downloads[0].payload);
  assert.equal(patch.project_id, "desktop");
  assert.equal(patch.changes.length, 1);
  assert.equal(patch.changes[0].before, "desktop text 1");
  assert.equal(patch.changes[0].after, "Nowa poprawka do desktopu");
});

test("matching saved patch restores corrected text without changing original source", async () => {
  const ux = boot(), original = source("same",2);
  await ux.importFile(original);
  assert.equal(ux.elements["corrections-file"].disabled, false);
  await ux.importPatch(JSON.parse(core.renderCorrections(original,{"seg-1":"Własna korekta."})));
  assert.match(ux.elements["edit-count"].textContent,/^1 poprawek/);
  ux.select(1);
  assert.equal(ux.elements["edit-text"].value,"Własna korekta.");
  ux.exportButtons[0].events.click();
  assert.match(ux.state.downloads[0].payload,/Własna korekta/);
  assert.equal(original.segments[1].text,"same text 1");
});
test("declined patch replacement preserves edits; explicit consent replaces them", async () => {
  const ux=boot(), original=source("same",2);
  await ux.importFile(original);
  ux.select(0);
  ux.elements["edit-text"].value="Moja praca";
  ux.elements["save-edit"].events.click();
  const saved=JSON.parse(core.renderCorrections(original,{"seg-0":"Nowa wartość"}));
  await ux.importPatch(saved);
  assert.equal(ux.elements["edit-text"].value,"Moja praca");
  assert.equal(ux.state.prompts.length,1);
  ux.state.allow=true;
  await ux.importPatch(saved);
  assert.equal(ux.elements["edit-text"].value,"Nowa wartość");
});
test("foreign patch is rejected and stale async patch cannot replace a new source", async () => {
  const ux=boot(),original=source("origin",2);
  await ux.importFile(original);
  const alien=JSON.parse(core.renderCorrections(source("other",2),{"seg-0":"Obcy"}));
  await ux.importPatch(alien);
  assert.match(ux.elements["status"].textContent,/Nie zastosowano/);
  assert.match(ux.elements["edit-count"].textContent,/^0 poprawek/);
  const saved=JSON.parse(core.renderCorrections(original,{"seg-0":"Nie zapisuj"}));
  let release;
  const pending=ux.importPatch(saved,()=>new Promise(resolve=>{release=resolve;}));
  await ux.importFile(source("newsource",1));
  release(JSON.stringify(saved));
  await pending;
  assert.match(ux.elements["match-count"].textContent,/^1 z 1/);
  assert.match(ux.elements["edit-count"].textContent,/^0 poprawek/);
});
test("newly entered edits while patch reads require fresh consent", async () => {
  const ux=boot(),original=source("original",2);
  await ux.importFile(original);
  const saved=JSON.parse(core.renderCorrections(original,{"seg-0":"Odtwórz"}));
  let release;
  const pending=ux.importPatch(saved,()=>new Promise(resolve=>{release=resolve;}));
  ux.select(0);
  ux.elements["edit-text"].value="Nowsza ręczna zmiana";
  ux.elements["edit-text"].events.input();
  release(JSON.stringify(saved));
  await pending;
  assert.equal(ux.elements["edit-text"].value,"Nowsza ręczna zmiana");
  assert.match(ux.elements["status"].textContent,/Zachowano późniejsze/);
  assert.equal(ux.state.prompts.length,1);
});

test("undo and redo restore a saved correction without changing the imported transcript", async () => {
  const ux = boot();
  const original = source("history", 2);
  await ux.importFile(original);
  ux.select(0);
  ux.elements["edit-text"].value = "Pierwsza korekta";
  ux.elements["save-edit"].events.click();
  assert.equal(ux.elements["undo-edit"].disabled, false);
  assert.equal(ux.elements["redo-edit"].disabled, true);
  ux.elements["undo-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "history text 0");
  assert.match(ux.elements["edit-count"].textContent, /^0 poprawek/);
  assert.equal(ux.elements["redo-edit"].disabled, false);
  ux.elements["redo-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "Pierwsza korekta");
  assert.match(ux.elements["edit-count"].textContent, /^1 poprawek/);
  assert.equal(original.segments[0].text, "history text 0");
});

test("multiple saved changes, reset and redo branch are bounded and correct", async () => {
  const ux = boot();
  await ux.importFile(source("history", 1));
  ux.select(0);
  ux.elements["edit-text"].value = "Wersja A";
  ux.elements["save-edit"].events.click();
  ux.elements["edit-text"].value = "Wersja B";
  ux.elements["save-edit"].events.click();
  ux.elements["reset-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "history text 0");
  ux.elements["undo-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "Wersja B");
  ux.elements["undo-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "Wersja A");
  ux.elements["redo-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "Wersja B");
  ux.elements["edit-text"].value = "Wersja C";
  ux.elements["save-edit"].events.click();
  assert.equal(ux.elements["redo-edit"].disabled, true);
});

test("history does not discard an unsaved draft without confirmation", async () => {
  const ux = boot();
  await ux.importFile(source("pending", 1));
  ux.select(0);
  ux.elements["edit-text"].value = "Zapisane";
  ux.elements["save-edit"].events.click();
  ux.elements["edit-text"].value = "Szkic jeszcze niezapisany";
  ux.elements["edit-text"].events.input();
  ux.elements["undo-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "Szkic jeszcze niezapisany");
  assert.equal(ux.state.prompts.length, 1);
  ux.state.allow = true;
  ux.elements["undo-edit"].events.click();
  assert.equal(ux.elements["edit-text"].value, "pending text 0");
});

test("new transcript and imported patch clear old document history", async () => {
  const ux = boot();
  await ux.importFile(source("first", 1));
  ux.select(0);
  ux.elements["edit-text"].value = "Old";
  ux.elements["save-edit"].events.click();
  ux.state.allow = true;
  await ux.importFile(source("second", 1));
  assert.equal(ux.elements["undo-edit"].disabled, true);
  ux.select(0);
  ux.elements["edit-text"].value = "Second";
  ux.elements["save-edit"].events.click();
  const patch = JSON.parse(core.renderCorrections(source("second", 1), {"seg-0": "Restored"}));
  await ux.importPatch(patch);
  assert.equal(ux.elements["edit-text"].value, "Restored");
  assert.equal(ux.elements["undo-edit"].disabled, true);
});

test("history does not grow without bound while saving thousands of changes", async () => {
  const ux = boot();
  await ux.importFile(source("many", 1));
  ux.select(0);
  for (let i = 0; i < 105; i++) {
    ux.elements["edit-text"].value = "Revision " + i;
    ux.elements["save-edit"].events.click();
  }
  for (let i = 0; i < 100; i++) ux.elements["undo-edit"].events.click();
  assert.equal(ux.elements["undo-edit"].disabled, true);
  assert.equal(ux.elements["edit-text"].value, "Revision 4");
});

test("local audio file remains an object URL; seeking uses segment time only after explicit click", async () => {
  const ux = boot();
  await ux.importFile(source("audio", 3));
  assert.equal(ux.elements["source-media"].disabled, false);
  assert.equal(ux.elements["seek-segment"].disabled, true);
  ux.importMedia();
  const player = ux.elements["source-player"];
  assert.equal(player.src, "blob:local");
  assert.equal(player.hidden, false);
  assert.equal(ux.elements["seek-segment"].disabled, true);
  ux.select(2);
  assert.equal(ux.elements["seek-segment"].disabled, false);
  player.readyState = 1;
  player.duration = 30;
  ux.elements["seek-segment"].events.click();
  assert.equal(player.currentTime, 3);
  assert.equal(player.playCount, undefined);
  assert.match(ux.elements["status"].textContent, /Przesunięto lokalny odtwarzacz/);
});

test("pending seek completes on metadata and rejects mismatched recording lengths", async () => {
  const ux = boot();
  await ux.importFile(source("audio", 3));
  ux.importMedia();
  ux.select(1);
  const player = ux.elements["source-player"];
  player.readyState = 0;
  ux.elements["seek-segment"].events.click();
  assert.match(ux.elements["status"].textContent, /Wczytywanie nagrania/);
  player.readyState = 1;
  player.duration = 1;
  player.events.loadedmetadata();
  assert.equal(player.currentTime, undefined);
  assert.match(ux.elements["status"].textContent, /wykracza poza/);
  player.duration = 4;
  ux.elements["seek-segment"].events.click();
  assert.equal(player.currentTime, 1.5);
});

test("replacing transcript revokes local recording URL and disables previous seek", async () => {
  const ux = boot();
  await ux.importFile(source("first", 2));
  ux.importMedia();
  ux.select(0);
  await ux.importFile(source("second", 1));
  assert.equal(ux.elements["source-player"].hidden, true);
  assert.equal(ux.elements["seek-segment"].disabled, true);
  assert.deepEqual(ux.state.revoked, ["blob:local"]);
  assert.equal(ux.elements["source-player"].src, undefined);
});

test("unsupported local codec is reported without exposing file paths or persisting audio", async () => {
  const ux = boot();
  await ux.importFile(source("audio", 1));
  ux.importMedia();
  ux.elements["source-player"].events.error();
  assert.equal(ux.elements["source-player"].hidden, true);
  assert.match(ux.elements["status"].textContent, /kodeka/);
  assert.equal(ux.state.revoked.length, 1);
  assert.equal(ux.elements["seek-segment"].disabled, true);
});

test("playhead selection jumps to matching paginated row with no linear DOM redraw", async () => {
  const ux = boot();
  await ux.importFile(source("timeline", 180));
  ux.importMedia();
  const player = ux.elements["source-player"];
  player.readyState = 1; player.duration = 1000;
  player.events.loadedmetadata();
  assert.equal(ux.elements["jump-playhead"].disabled, false);
  player.currentTime = 150 * 1.5 + 0.15;
  ux.elements["jump-playhead"].events.click();
  assert.match(ux.elements["selected-label"].textContent, /seg-150/);
  assert.equal(ux.elements["page-number"].textContent, "Strona 3 / 3");
  assert.equal(ux.elements["segment-rows"].children.length, 30);
  assert.equal(ux.elements["edit-text"].value, "timeline text 150");
});
test("playhead jump reveals filtered-out segment only after safe draft confirmation", async () => {
  const ux = boot();
  await ux.importFile(source("classes", 5));
  ux.importMedia();
  ux.elements["source-player"].readyState = 1;
  ux.elements["source-player"].duration = 15;
  ux.elements["source-player"].events.loadedmetadata();
  ux.elements["search"].value = "text 0";
  ux.elements["search"].events.input();
  ux.select(0);
  ux.elements["edit-text"].value = "Mój niezapisany szkic";
  ux.elements["edit-text"].events.input();
  ux.elements["source-player"].currentTime = 3.2;
  ux.elements["jump-playhead"].events.click();
  assert.equal(ux.elements["search"].value, "text 0");
  assert.match(ux.elements["selected-label"].textContent, /seg-0/);
  assert.equal(ux.elements["edit-text"].value, "Mój niezapisany szkic");
  assert.equal(ux.state.prompts.length, 1);
  ux.state.allow = true;
  ux.elements["jump-playhead"].events.click();
  assert.equal(ux.elements["search"].value, "");
  assert.match(ux.elements["selected-label"].textContent, /seg-2/);
  assert.equal(ux.elements["edit-text"].value, "classes text 2");
});
test("playhead jumper stays disabled before metadata or after removing source", async () => {
  const ux = boot();
  await ux.importFile(source("media", 2));
  assert.equal(ux.elements["jump-playhead"].disabled, true);
  ux.importMedia();
  assert.equal(ux.elements["jump-playhead"].disabled, true);
  ux.elements["source-player"].readyState = 1;
  ux.elements["source-player"].events.loadedmetadata();
  assert.equal(ux.elements["jump-playhead"].disabled, false);
  ux.elements["source-player"].currentTime = Number.NaN;
  ux.elements["jump-playhead"].events.click();
  assert.match(ux.elements["status"].textContent, /prawidłowego czasu/);
  ux.elements["source-player"].events.error();
  assert.equal(ux.elements["jump-playhead"].disabled, true);
});
