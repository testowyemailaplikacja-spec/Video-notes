"use strict";
// Real Chromium smoke of web/index.html opened as file://, no npm or web API.
// Uses Node 22 built-in WebSocket and Chrome DevTools Protocol on loopback.
const assert = require("node:assert/strict");
const cp = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const {pathToFileURL} = require("node:url");

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function httpJSON(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, {timeout: 2500}, response => {
      let data = "";
      response.setEncoding("utf8");
      response.on("data", chunk => { data += chunk; });
      response.on("end", () => {
        try { resolve(JSON.parse(data)); } catch (error) { reject(error); }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => req.destroy(new Error("CDP HTTP timeout")));
  });
}

async function browserScenario() {
  const readyUntil = Date.now() + 6000;
  while ((document.readyState !== "complete" || !window.VideoNotesWebCore) &&
         Date.now() < readyUntil) {
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  const input = document.getElementById("source-file");
  const label = document.getElementById("match-count");
  const editor = document.getElementById("edit-text");
  const status = document.getElementById("status");
  if (!input || !label || !editor || !status) throw new Error("Brak wymaganych elementów KWN. URL=" + location.href + " ready=" + document.readyState + " title=" + document.title);
  const fixture = {
    schema: "videonotes-export-v1", project_id: "chromium-demo",
    language: "pl", complete: true, segments: [
      {id: "s-001", start_ms: 0, end_ms: 1000, text: "Pierwsza wypowiedź."},
      {id: "s-002", start_ms: 2000, end_ms: 3000, text: "Druga wypowiedź."}
    ]
  };
  const file = new File([JSON.stringify(fixture)], "chrome-fixture.json", {type: "application/json"});
  Object.defineProperty(input, "files", {configurable: true, value: [file]});
  input.dispatchEvent(new Event("change", {bubbles: true}));
  const until = Date.now() + 5000;
  while (!label.textContent.startsWith("2 z 2") && Date.now() < until) {
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  if (!label.textContent.startsWith("2 z 2")) {
    throw new Error("Import lokalnego JSON nie zakończył się: " + status.textContent);
  }
  const historyUndo = document.getElementById("undo-edit");
  const historyRedo = document.getElementById("redo-edit");
  if (!historyUndo || !historyRedo || !historyUndo.disabled || !historyRedo.disabled) {
    throw new Error("Missing or incorrectly initialized edit history controls");
  }
  const first = document.querySelector("#segment-rows button.segment-choice");
  if (!first) throw new Error("Brak przycisku do wyboru segmentu");
  first.click();
  if (editor.value !== "Pierwsza wypowiedź.") throw new Error("Błędna treść edytora");
  editor.value = "Poprawiony tekst użytkownika";
  editor.dispatchEvent(new Event("input", {bubbles: true}));
  document.querySelector("#segment-rows button.segment-choice").click();
  if (editor.value !== "Poprawiony tekst użytkownika") {
    throw new Error("Clicking selected row discarded unsaved textarea draft");
  }

  // Capture the real generated Blob without writing a file during headless CI.
  const nativeCreateObjectURL = URL.createObjectURL.bind(URL);
  const nativeRevokeObjectURL = URL.revokeObjectURL.bind(URL);
  const captures = [];
  URL.createObjectURL = function (blob) { captures.push(blob); return "blob:synthetic-smoke"; };
  URL.revokeObjectURL = function () {};
  HTMLAnchorElement.prototype.click = function () {};
  const txt = document.querySelector('button[data-export="transcript.txt"]');
  if (!txt) throw new Error("Brak eksportu TXT");
  txt.click();
  if (captures.length || !status.textContent.includes("Najpierw kliknij")) {
    throw new Error("Eksport pominął niezapisany szkic lub nie pokazał ostrzeżenia");
  }
  document.getElementById("save-edit").click();
  if (historyUndo.disabled || !historyRedo.disabled) throw new Error("Undo did not become available");
  historyUndo.click();
  if (editor.value !== "Pierwsza wypowiedź." || historyRedo.disabled) {
    throw new Error("Undo failed to restore source text");
  }
  historyRedo.click();
  if (editor.value !== "Poprawiony tekst użytkownika") {
    throw new Error("Redo failed to restore saved edit");
  }
  txt.click();
  if (captures.length !== 1) throw new Error("Nie wygenerowano lokalnego TXT po zapisie");
  const text = await captures[0].text();
  if (!text.includes("Poprawiony tekst użytkownika")) throw new Error("Eksport nie zawiera poprawki");

  // The real browser must also produce a minimal reversible desktop patch.
  const correctionButton = document.querySelector('button[data-export="web-corrections.json"]');
  if (!correctionButton) throw new Error("Brak przycisku wymiany poprawek desktop");
  correctionButton.click();
  if (captures.length !== 2) throw new Error("Brak paczki poprawek w realnej przeglądarce");
  const patch = JSON.parse(await captures[1].text());
  if (patch.schema !== "videonotes-web-corrections-v1" || patch.project_id !== "chromium-demo" ||
      patch.changes.length !== 1 || patch.changes[0].before !== "Pierwsza wypowiedź." ||
      patch.changes[0].after !== "Poprawiony tekst użytkownika") {
    throw new Error("Niezgodny format poprawek między WWW i desktopem");
  }

  // Round-trip a previously downloaded correction pack on the same original.
  const fileInput = document.getElementById("corrections-file");
  if (!fileInput || fileInput.disabled) throw new Error("No saved correction import input");
  window.confirm = () => true;
  Object.defineProperty(fileInput, "files", {configurable:true,value:[
    new File([JSON.stringify(patch)],"web-corrections.json",{type:"application/json"})
  ]});
  fileInput.dispatchEvent(new Event("change",{bubbles:true}));
  const restoredUntil=Date.now()+5000;
  while(!status.textContent.includes("Przywrócono")&&Date.now()<restoredUntil) {
    await new Promise(resolve=>setTimeout(resolve,25));
  }
  if (!status.textContent.includes("Przywrócono 1 poprawek") ||
      editor.value !== "Poprawiony tekst użytkownika") {
    throw new Error("Saved patch failed to restore exact corrected text");
  }
  Object.defineProperty(fileInput, "files", {configurable:true,value:[
    new File([JSON.stringify({...patch,project_id:"foreign"})],"foreign.json",{type:"application/json"})
  ]});
  fileInput.dispatchEvent(new Event("change",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,100));
  if(!status.textContent.includes("Nie zastosowano") ||
     editor.value!=="Poprawiony tekst użytkownika") {
    throw new Error("Foreign saved patch changed or erased existing corrections");
  }
  // A rejected replacement may not silently lose the saved correction.
  window.confirm = () => false;
  const newer = new File([JSON.stringify({...fixture, project_id: "another", segments: []})],
                         "replacement.json", {type: "application/json"});
  Object.defineProperty(input, "files", {configurable: true, value: [newer]});
  input.dispatchEvent(new Event("change", {bubbles: true}));
  await new Promise(resolve => setTimeout(resolve, 100));
  if (!label.textContent.startsWith("2 z 2")) throw new Error("Anulowany import zastąpił dokument");
  if (!document.getElementById("edit-count").textContent.startsWith("1 poprawek")) {
    throw new Error("Anulowany import usunął poprawki");
  }

  // Check real local media playback, not a fake Blob URL. The WAV is synthetic,
  // created in this browser process; no speech or private recording is involved.
  URL.createObjectURL = nativeCreateObjectURL;
  URL.revokeObjectURL = nativeRevokeObjectURL;
  const rate=8000, count=rate*4;
  const buffer=new ArrayBuffer(44+count), view=new DataView(buffer);
  function waveStr(offset,value) {
    for (let i=0;i<value.length;i++) view.setUint8(offset+i,value.charCodeAt(i));
  }
  waveStr(0,"RIFF"); view.setUint32(4,36+count,true); waveStr(8,"WAVE");
  waveStr(12,"fmt "); view.setUint32(16,16,true);
  view.setUint16(20,1,true); view.setUint16(22,1,true);
  view.setUint32(24,rate,true); view.setUint32(28,rate,true);
  view.setUint16(32,1,true); view.setUint16(34,8,true);
  waveStr(36,"data"); view.setUint32(40,count,true);
  new Uint8Array(buffer,44).fill(128);
  const mediaInput=document.getElementById("source-media");
  const mediaPlayer=document.getElementById("source-player");
  const seekButton=document.getElementById("seek-segment");
  if(!mediaInput||mediaInput.disabled||!mediaPlayer||!seekButton) {
    throw new Error("Missing local playback UI");
  }
  Object.defineProperty(mediaInput,"files",{configurable:true,value:[
    new File([buffer],"synthetic-silence.wav",{type:"audio/wav"})
  ]});
  mediaInput.dispatchEvent(new Event("change",{bubbles:true}));
  const mediaUntil=Date.now()+7000;
  while(mediaPlayer.readyState<1 && Date.now()<mediaUntil) {
    await new Promise(resolve=>setTimeout(resolve,50));
  }
  if(mediaPlayer.readyState<1)throw new Error("Local synthetic WAV metadata not loaded: "+status.textContent);
  document.querySelectorAll("#segment-rows button.segment-choice")[1].click();
  if(seekButton.disabled)throw new Error("Seek remains disabled after selecting a segment");
  seekButton.click();
  const seekUntil=Date.now()+3000;
  while(Math.abs(mediaPlayer.currentTime-2)>0.2 && Date.now()<seekUntil) {
    await new Promise(resolve=>setTimeout(resolve,30));
  }
  if(Math.abs(mediaPlayer.currentTime-2)>0.2) {
    throw new Error("Local WAV seek to 2s failed: "+mediaPlayer.currentTime);
  }
  if(!mediaPlayer.paused)throw new Error("Media playback started without user consent");
  // Reverse direction: use the player's clock to reveal the matching cue.
  const playhead=document.getElementById("jump-playhead");
  if(!playhead||playhead.disabled)throw new Error("Playhead navigation disabled after media metadata");
  document.querySelectorAll("#segment-rows button.segment-choice")[0].click();
  mediaPlayer.currentTime=2.05;
  playhead.click();
  if(!document.getElementById("selected-label").textContent.includes("s-002") ||
     editor.value!=="Druga wypowiedź.") {
    throw new Error("Playhead did not locate second segment");
  }
  // WEB-02 automated subtest: genuine browser import/search/page navigation with 50k rows.
  // The fixture is synthetic, never contains a private recording, and stays within MAX_BYTES.
  window.confirm = () => true;
  const largeFixture = {
    schema: "videonotes-export-v1", project_id: "kwn-50k-synthetic",
    language: "pl", complete: true,
    segments: Array.from({length: 50000}, (_, i) => ({
      id: "large-" + i, start_ms: i * 1000, end_ms: i * 1000 + 750,
      text: "Wypowiedź " + i + " znacznik-" + i
    }))
  };
  const largeFile = new File([JSON.stringify(largeFixture)], "synthetic-50k.json",
                             {type: "application/json"});
  if (largeFile.size > window.VideoNotesWebCore.MAX_BYTES) throw new Error("50k fixture exceeds file cap");
  Object.defineProperty(input, "files", {configurable: true, value: [largeFile]});
  const largeStarted = performance.now();
  input.dispatchEvent(new Event("change", {bubbles: true}));
  const largeDeadline = Date.now() + 20000;
  while (!label.textContent.startsWith("50000 z 50000") && Date.now() < largeDeadline) {
    await new Promise(resolve => setTimeout(resolve, 30));
  }
  if (!label.textContent.startsWith("50000 z 50000")) throw new Error("50k import failed: " + status.textContent);
  if (!mediaPlayer.hidden || !seekButton.disabled) throw new Error("Replacing the source retained a foreign recording");
  if (document.querySelectorAll("#segment-rows button.segment-choice").length !== 75) {
    throw new Error("50k table was not restricted to 75 visible buttons");
  }
  const search = document.getElementById("search");
  search.value = "znacznik-49999";
  search.dispatchEvent(new Event("input", {bubbles: true}));
  if (!label.textContent.startsWith("1 z 50000")) throw new Error("50k search did not find last segment");
  if (!document.querySelector("#segment-rows button.segment-choice")?.textContent.includes("49999")) {
    throw new Error("50k search returned wrong segment");
  }
  search.value = "";
  search.dispatchEvent(new Event("input", {bubbles: true}));
  document.getElementById("next").click();
  if (!document.getElementById("page-number").textContent.includes("Strona 2 / 667")) {
    throw new Error("50k pagination failed");
  }
  document.getElementById("previous").click();
  const firstLarge = document.querySelector("#segment-rows button.segment-choice");
  firstLarge.focus();
  firstLarge.click();
  const refreshed = document.querySelector("#segment-rows button.segment-choice");
  if (document.activeElement !== refreshed || refreshed.getAttribute("aria-pressed") !== "true" ||
      refreshed.getAttribute("aria-controls") !== "edit-text") {
    throw new Error("Selecting a segment lost keyboard focus or ARIA selection state");
  }
  if (!document.querySelector("table caption") ||
      document.querySelector(".editor").getAttribute("aria-labelledby") !== "editor-heading") {
    throw new Error("Missing accessible table/editor labeling");
  }
  const largeMs = performance.now() - largeStarted;
  if (largeMs > 15000) throw new Error("50k browser interaction exceeded 15s: " + Math.round(largeMs));
  const network = performance.getEntriesByType("resource")
    .filter(item => /^https?:/i.test(item.name)).map(item => item.name);
  return {protocol: location.protocol, imported: fixture.segments.length,
          largeSegments: largeFixture.segments.length, largeInteractionMs: Math.round(largeMs),
          focusPreserved: true, exportContainsEdit: true, deniedReplacePreserved: true,
          networkRequests: network.length};
}

async function prepareRealDownloadFixture() {
  const untilReady = Date.now() + 6000;
  while ((!window.VideoNotesWebCore || document.readyState !== "complete") && Date.now() < untilReady) {
    await new Promise(resolve => setTimeout(resolve, 40));
  }
  const fixture = {
    schema: "videonotes-export-v1", project_id: "real-download-smoke",
    language: "pl", complete: true,
    segments: [
      {id: "seg-001", start_ms: 0, end_ms: 1700, text: "Fragment <oryginalny>."},
      {id: "seg-002", start_ms: 2000, end_ms: 3400, text: "Zdanie drugie."}
    ]
  };
  const input = document.getElementById("source-file");
  if (!input) throw new Error("Missing file picker");
  Object.defineProperty(input, "files", {configurable: true, value: [
    new File([JSON.stringify(fixture)], "download-input.json", {type: "application/json"})
  ]});
  input.dispatchEvent(new Event("change", {bubbles: true}));
  const deadline = Date.now() + 6000;
  while (!document.getElementById("match-count").textContent.startsWith("2 z 2") && Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 40));
  }
  if (!document.getElementById("match-count").textContent.startsWith("2 z 2")) {
    throw new Error("Download fixture import did not complete");
  }
  const first = document.querySelector("#segment-rows .segment-choice");
  first.click();
  const edit = document.getElementById("edit-text");
  edit.value = "Zażółć & <B>\\nZapisane po korekcie.";
  edit.dispatchEvent(new Event("input", {bubbles: true}));
  document.getElementById("save-edit").click();
  return {
    imported: 2,
    corrections: document.getElementById("edit-count").textContent,
    source: fixture.segments[0].text
  };
}

function assertRealDownloads(directory) {
  // These are disk-backed bytes, not a mocked createObjectURL/anchor click.
  const contents = Object.fromEntries(
    ["transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json", "web-corrections.json"]
      .map(name => [name, fs.readFileSync(path.join(directory, name), "utf8")])
  );
  assert.match(contents["transcript.txt"], /Zażółć & <B>/);
  assert.match(contents["transcript.txt"], /Zdanie drugie/);
  assert.match(contents["transcript.srt"], /00:00:00,000 --> 00:00:01,700/);
  assert.match(contents["transcript.vtt"], /Zażółć &amp; &lt;B&gt;/);
  const transcript = JSON.parse(contents["transcript.json"]);
  assert.equal(transcript.project_id, "real-download-smoke");
  assert.equal(transcript.segments[0].text, "Zażółć & <B>\\nZapisane po korekcie.");
  assert.equal(transcript.segments[1].text, "Zdanie drugie.");
  const patch = JSON.parse(contents["web-corrections.json"]);
  assert.equal(patch.schema, "videonotes-web-corrections-v1");
  assert.equal(patch.project_id, "real-download-smoke");
  assert.equal(patch.changes.length, 1);
  assert.equal(patch.changes[0].before, "Fragment <oryginalny>.");
  assert.equal(patch.changes[0].after, transcript.segments[0].text);
  return Object.keys(contents).length;
}

async function main() {
  const root = path.resolve(__dirname, "../web/index.html");
  if (!fs.existsSync(root)) throw new Error("web/index.html missing");
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "kwn-chrome-"));
  const realDownloads = fs.mkdtempSync(path.join(os.tmpdir(), "kwn-real-download-"));
  const browserPath = process.env.CHROME_BIN || "chromium";
  const browser = cp.spawn(browserPath, [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    "--disable-background-networking", "--no-first-run", "--no-default-browser-check",
    "--remote-allow-origins=*", "--remote-debugging-port=0",
    "--user-data-dir=" + userData, "about:blank"
  ], {stdio: ["ignore", "ignore", "pipe"]});
  let chromeErrors = "";
  browser.stderr.on("data", chunk => {
    chromeErrors = (chromeErrors + String(chunk)).slice(-4096);
  });
  let socket;
  try {
    let port = null;
    for (let i = 0; i < 300; i++) {
      if (browser.exitCode !== null || browser.signalCode !== null) throw new Error("Chromium exited before CDP became ready; " + chromeErrors.slice(-1500));
      const portFile = path.join(userData, "DevToolsActivePort");
      if (fs.existsSync(portFile)) {
        // Windows Edge/Chrome can expose this file before releasing its write
        // lock. EBUSY/EACCES is transient while CDP is starting.
        try {
          port = Number(fs.readFileSync(portFile, "utf8").split(/\r?\n/)[0]);
          if (port) break;
        } catch (error) {
          if (!["EBUSY", "EACCES", "EPERM", "ENOENT"].includes(error.code)) throw error;
        }
      }
      await pause(100);
    }
    if (!port) throw new Error("Chromium CDP port unavailable; stderr tail: " + chromeErrors.slice(-1500));
    let page = null;
    for (let i = 0; i < 80; i++) {
      try {
        const pages = await httpJSON("http://127.0.0.1:" + port + "/json/list");
        page = pages.find(item => item.type === "page" && item.url === "about:blank") ||
               pages.find(item => item.type === "page");
      } catch (_error) {
        // The port file can appear before CDP HTTP starts accepting requests.
      }
      if (page) break;
      await pause(150);
    }
    if (!page?.webSocketDebuggerUrl) throw new Error("Cannot locate browser page CDP target");
    socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, {once: true});
      socket.addEventListener("error", reject, {once: true});
    });
    const cdp = (id, method, params, timeoutMs = 20000) => new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        socket.removeEventListener("message", onMessage);
        reject(new Error("CDP request timeout: " + method));
      }, timeoutMs);
      function onMessage(event) {
        const data = JSON.parse(String(event.data));
        if (data.id !== id) return;
        clearTimeout(timeout);
        socket.removeEventListener("message", onMessage);
        if (data.error) return reject(new Error(JSON.stringify(data.error)));
        if (data.result?.exceptionDetails) {
          return reject(new Error(data.result.exceptionDetails.text + " " +
            (data.result.exceptionDetails.exception?.description || "")));
        }
        resolve(data.result);
      }
      socket.addEventListener("message", onMessage);
      socket.send(JSON.stringify({id, method, params}));
    });
    // CDP observes attempted network requests, not just successful resource
    // timing entries. This includes failed outbound fetch attempts by the page.
    let outboundAttempts = 0;
    socket.addEventListener("message", event => {
      try {
        const data = JSON.parse(String(event.data));
        if (data.method === "Network.requestWillBeSent" &&
            /^https?:/i.test(data.params?.request?.url || "")) {
          outboundAttempts += 1;
        }
      } catch (_error) {
        // Other CDP events are irrelevant; never log their user data.
      }
    });
    await cdp(1, "Page.enable", {});
    await cdp(12, "Network.enable", {});
    const navigation = await cdp(2, "Page.navigate", {url: pathToFileURL(root).href});
    if (navigation.errorText) throw new Error("Chrome cannot navigate to local KWN file: " + navigation.errorText);
    await pause(800);
    const expression = "(" + browserScenario.toString() + ")()";
    let evaluated;
    try {
      evaluated = await cdp(3, "Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true}, 60000);
    } catch (error) {
      if (!String(error.message).includes("Execution context was destroyed")) throw error;
      await pause(1200);
      evaluated = await cdp(4, "Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true}, 60000);
    }
    const payload = evaluated?.result?.value;
    assert.equal(payload.protocol, "file:");
    assert.equal(payload.imported, 2);
    assert.equal(payload.largeSegments, 50000);
    assert.equal(payload.focusPreserved, true);
    process.stdout.write("50k synthetic KWN browser interactions in " + payload.largeInteractionMs + "ms PASS\\n");
    assert.equal(payload.exportContainsEdit, true);
    assert.equal(payload.deniedReplacePreserved, true);
    assert.equal(payload.networkRequests, 0);
    assert.equal(outboundAttempts, 0, "Page attempted an HTTP(S) request under file://");
    process.stdout.write("Chromium file:// KWN import/edit/export/replace smoke PASS\n");
    // A separate fresh page avoids the in-memory anchor/Blob mocks used by
    // cross-browser functional smoke; verify what really lands on disk.
    try {
      await cdp(10, "Browser.setDownloadBehavior", {behavior: "allow", downloadPath: realDownloads});
    } catch (_error) {
      await cdp(11, "Page.setDownloadBehavior", {behavior: "allow", downloadPath: realDownloads});
    }
    const fresh = await cdp(12, "Page.navigate", {url: pathToFileURL(root).href});
    if (fresh.errorText) throw new Error("Fresh download page refused: " + fresh.errorText);
    const prepared = await cdp(13, "Runtime.evaluate", {
      expression: "(" + prepareRealDownloadFixture.toString() + ")()",
      awaitPromise: true, returnByValue: true, userGesture: true
    }, 20000);
    assert.equal(prepared.result.value.imported, 2);
    assert.match(prepared.result.value.corrections, /1 poprawek/);
    const names = ["transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json", "web-corrections.json"];
    for (let i = 0; i < names.length; i++) {
      const name = names[i];
      const trigger = await cdp(20 + i, "Runtime.evaluate", {
        expression: "document.querySelector(" + JSON.stringify('button[data-export="' + name + '"]') + ").click()",
        userGesture: true, returnByValue: true
      });
      if (trigger.result?.subtype === "error") throw new Error("Download click failed: " + name);
      let downloaded = false;
      for (let attempt = 0; attempt < 120; attempt++) {
        const files = fs.readdirSync(realDownloads);
        const complete = path.join(realDownloads, name);
        if (files.includes(name) && fs.statSync(complete).size > 0 &&
            !files.some(file => file.endsWith(".crdownload"))) {
          downloaded = true;
          break;
        }
        await pause(60);
      }
      if (!downloaded) throw new Error("Browser did not save expected file: " + name);
    }
    assert.equal(assertRealDownloads(realDownloads), 5);
    process.stdout.write("Chrome/Edge/Chromium real local downloaded TXT/SRT/VTT/JSON/patch bytes PASS\n");
  } finally {
    if (socket) socket.close();
    const exited = new Promise(resolve => {
      if (browser.exitCode !== null) return resolve();
      browser.once("exit", resolve);
      setTimeout(resolve, 3000);
    });
    browser.kill("SIGTERM");
    await exited;
    for (const temporary of [userData, realDownloads]) {
      try {
        fs.rmSync(temporary, {recursive: true, force: true, maxRetries: 10, retryDelay: 150});
      } catch (error) {
        process.stderr.write("Chromium temporary-profile cleanup warning: " + error.code + "\n");
      }
    }
  }
}
// Reuse the same real-browser scenario from Firefox WebDriver without executing CDP.
module.exports = {browserScenario};
if (require.main === module) {
  main().catch(error => { process.stderr.write(String(error.stack || error) + "\n"); process.exitCode = 1; });
}
