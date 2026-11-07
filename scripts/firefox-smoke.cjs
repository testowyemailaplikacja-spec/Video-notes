"use strict";
// Real Firefox + geckodriver acceptance subtest for local file:// KWN.
// Uses the Node 22 fetch API and W3C WebDriver on loopback only: no npm or cloud.
const assert = require("node:assert/strict");
const child = require("node:child_process");
const net = require("node:net");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {browserScenario} = require("./browser-smoke.cjs");

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const port = server.address().port;
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  return port;
}
async function webdriver(base, method, endpoint, data, timeout = 60000) {
  const response = await fetch(base + endpoint, {
    method, headers: {"Content-Type": "application/json"},
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(timeout)
  });
  const result = await response.json();
  if (!response.ok || result?.value?.error) {
    throw new Error("WebDriver " + method + " " + endpoint + ": " + JSON.stringify(result).slice(0, 1800));
  }
  return result.value;
}
async function main() {
  const port = await freePort();
  const base = "http://127.0.0.1:" + port;
  const driver = child.spawn(process.env.GECKODRIVER_BIN || "geckodriver",
    ["--host", "127.0.0.1", "--port", String(port)],
    {stdio: ["ignore", "ignore", "pipe"]});
  let stderr = "";
  driver.stderr.on("data", chunk => { stderr = (stderr + String(chunk)).slice(-5000); });
  let session;
  try {
    let ready = false;
    for (let i = 0; i < 200; i++) {
      if (driver.exitCode !== null || driver.signalCode !== null) {
        throw new Error("geckodriver exited before ready: " + stderr);
      }
      try {
        const status = await webdriver(base, "GET", "/status", undefined, 1000);
        if (status?.ready) { ready = true; break; }
      } catch (_error) {
        // Wait until the local WebDriver listener is ready.
      }
      await pause(150);
    }
    if (!ready) throw new Error("geckodriver did not become ready: " + stderr);
    const created = await webdriver(base, "POST", "/session", {
      capabilities: {alwaysMatch: {
        browserName: "firefox",
        "moz:firefoxOptions": {args: ["-headless"], prefs: {
          "app.update.enabled": false, "browser.shell.checkDefaultBrowser": false
        }}
      }}
    }, 90000);
    session = created.sessionId;
    if (!session) throw new Error("Firefox session ID missing");
    await webdriver(base, "POST", "/session/" + session + "/timeouts", {script: 120000});
    const url = pathToFileURL(path.resolve(__dirname, "../web/index.html")).href;
    await webdriver(base, "POST", "/session/" + session + "/url", {url});
    const js = "const done = arguments[arguments.length - 1]; (" +
      browserScenario.toString() +
      ")().then(data => done({ok: true, data}), error => done({ok: false, error: String(error.stack || error)}));";
    const run = await webdriver(base, "POST", "/session/" + session + "/execute/async",
      {script: js, args: []}, 150000);
    if (!run?.ok) throw new Error("Firefox browser scenario failed: " + String(run?.error));
    assert.equal(run.data.protocol, "file:");
    assert.equal(run.data.imported, 2);
    assert.equal(run.data.largeSegments, 50000);
    assert.equal(run.data.focusPreserved, true);
    assert.equal(run.data.exportContainsEdit, true);
    assert.equal(run.data.deniedReplacePreserved, true);
    assert.equal(run.data.networkRequests, 0);
    process.stdout.write("Firefox file:// import/edit/50k/focus/zero-resource smoke PASS (" +
      run.data.largeInteractionMs + "ms)\n");
  } finally {
    if (session) {
      try { await webdriver(base, "DELETE", "/session/" + session, undefined, 10000); }
      catch (error) { process.stderr.write("Firefox session cleanup: " + error.message + "\n"); }
    }
    if (driver.exitCode === null) {
      driver.kill("SIGTERM");
      await Promise.race([
        new Promise(resolve => driver.once("exit", resolve)),
        pause(3000)
      ]);
      if (driver.exitCode === null) driver.kill("SIGKILL");
    }
  }
}
main().catch(error => { process.stderr.write(String(error.stack || error) + "\n"); process.exitCode = 1; });
