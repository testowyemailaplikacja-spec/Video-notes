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
  const first = document.querySelector("#segment-rows button.segment-choice");
  if (!first) throw new Error("Brak przycisku do wyboru segmentu");
  first.click();
  if (editor.value !== "Pierwsza wypowiedź.") throw new Error("Błędna treść edytora");
  editor.value = "Poprawiony tekst użytkownika";
  editor.dispatchEvent(new Event("input", {bubbles: true}));

  // Capture the real generated Blob without writing a file during headless CI.
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
  txt.click();
  if (captures.length !== 1) throw new Error("Nie wygenerowano lokalnego TXT po zapisie");
  const text = await captures[0].text();
  if (!text.includes("Poprawiony tekst użytkownika")) throw new Error("Eksport nie zawiera poprawki");

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
  const network = performance.getEntriesByType("resource")
    .filter(item => /^https?:/i.test(item.name)).map(item => item.name);
  return {protocol: location.protocol, imported: fixture.segments.length,
          exportContainsEdit: true, deniedReplacePreserved: true,
          networkRequests: network.length};
}

async function main() {
  const root = path.resolve(__dirname, "../web/index.html");
  if (!fs.existsSync(root)) throw new Error("web/index.html missing");
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "kwn-chrome-"));
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
        port = Number(fs.readFileSync(portFile, "utf8").split(/\r?\n/)[0]);
        if (port) break;
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
    await cdp(1, "Page.enable", {});
    const navigation = await cdp(2, "Page.navigate", {url: pathToFileURL(root).href});
    if (navigation.errorText) throw new Error("Chrome cannot navigate to local KWN file: " + navigation.errorText);
    await pause(800);
    const expression = "(" + browserScenario.toString() + ")()";
    let evaluated;
    try {
      evaluated = await cdp(3, "Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
    } catch (error) {
      if (!String(error.message).includes("Execution context was destroyed")) throw error;
      await pause(1200);
      evaluated = await cdp(4, "Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
    }
    const payload = evaluated?.result?.value;
    assert.equal(payload.protocol, "file:");
    assert.equal(payload.imported, 2);
    assert.equal(payload.exportContainsEdit, true);
    assert.equal(payload.deniedReplacePreserved, true);
    assert.equal(payload.networkRequests, 0);
    process.stdout.write("Chromium file:// KWN import/edit/export/replace smoke PASS\n");
  } finally {
    if (socket) socket.close();
    const exited = new Promise(resolve => {
      if (browser.exitCode !== null) return resolve();
      browser.once("exit", resolve);
      setTimeout(resolve, 3000);
    });
    browser.kill("SIGTERM");
    await exited;
    try {
      fs.rmSync(userData, {recursive: true, force: true, maxRetries: 10, retryDelay: 150});
    } catch (error) {
      process.stderr.write("Chromium temporary-profile cleanup warning: " + error.code + "\n");
    }
  }
}
main().catch(error => { process.stderr.write(String(error.stack || error) + "\n"); process.exitCode = 1; });
