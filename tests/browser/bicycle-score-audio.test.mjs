import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const scorePath = "/docs/practiced-songs/bicycle-built-for-two-grand-staff.html";
let browser;
let server;
let origin;

before(async () => {
  server = createServer(async (request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    if (pathname !== scorePath && !/^\/public\/audio\/[\w.-]+$/.test(pathname)) {
      response.writeHead(404).end();
      return;
    }
    try {
      const content = await readFile(path.join(root, pathname));
      const mime = pathname.endsWith(".js") ? "text/javascript" : pathname.endsWith(".wasm") ? "application/wasm" : "text/html";
      response.writeHead(200, { "Content-Type": mime }).end(content);
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true,
    executablePath: process.env.PIANO_CHROMIUM_PATH || undefined });
});

after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

async function newScore(t) {
  const page = await browser.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  t.after(async () => { await page.close(); assert.deepEqual(errors, []); });
  // The new default must work even when the optional legacy CDN is offline.
  await page.route("https://cdnjs.cloudflare.com/**", route => route.abort());
  await page.addInitScript(() => {
    window.audioChecks = [];
    window.scoreContexts = [];
    const Context = window.AudioContext;
    window.AudioContext = new Proxy(Context, {
      construct(target, args) {
        const context = Reflect.construct(target, args);
        window.scoreContexts.push(context);
        return context;
      },
    });
    const Worklet = window.AudioWorkletNode;
    window.AudioWorkletNode = new Proxy(Worklet, {
      construct(target, args) {
        const node = Reflect.construct(target, args);
        const splitter = args[0].createChannelSplitter(2);
        const analysers = [args[0].createAnalyser(), args[0].createAnalyser()];
        node.connect(splitter);
        analysers.forEach((analyser, channel) => splitter.connect(analyser, channel));
        const entry = { context: args[0], node, analysers, sent: [], notices: [] };
        const post = node.port.postMessage.bind(node.port);
        node.port.postMessage = message => { entry.sent.push(message); post(message); };
        node.port.addEventListener("message", event => entry.notices.push(event.data));
        node.port.start();
        window.audioChecks.push(entry);
        return node;
      },
    });
  });
  await page.goto(origin + scorePath);
  return page;
}

const levels = page => page.evaluate(() => window.audioChecks.at(-1).analysers.map(analyser => {
  const samples = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(samples);
  return Math.sqrt(samples.reduce((sum, x) => sum + x * x, 0) / samples.length);
}));
const onsets = page => page.evaluate(() => window.audioChecks.at(-1).sent.filter(message => message.kind === 1).map(message => message.note));
const clearSent = page => page.evaluate(() => { window.audioChecks.at(-1).sent.length = 0; });
async function waitForSound(page) {
  await page.waitForFunction(() => {
    const analyser = window.audioChecks.at(-1)?.analysers[0];
    if (!analyser) return false;
    const samples = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(samples);
    return samples.some(sample => Math.abs(sample) > 0.0001);
  });
}
async function stop(page) {
  await page.locator("#btn-stop").click();
  await page.waitForTimeout(180);
  assert.deepEqual(await levels(page), [0, 0]);
}

test("grand staff plays both hands, previews, track isolation, pause and timbre changes through Rust", { timeout: 45000 }, async t => {
  const page = await newScore(t);
  assert.equal(await page.locator("#timbre-basic").getAttribute("class"), "track-btn active");
  assert.equal(await page.locator("#reverb-slider").isDisabled(), true);
  await page.locator("#btn-play").click();
  await waitForSound(page);
  assert.deepEqual((await onsets(page)).sort((a, b) => a - b), [41, 65]);
  const both = await levels(page);
  assert.ok(both.every(level => level > 0.0001));
  await page.locator("#btn-play").click(); // pause
  await page.waitForTimeout(180);
  assert.deepEqual(await levels(page), [0, 0]);
  await page.locator("#btn-play").click(); // resume
  await waitForSound(page);
  await stop(page);

  await clearSent(page);
  await page.locator('.event-group[data-hand="rh"]').first().click();
  await waitForSound(page);
  assert.deepEqual(await onsets(page), [65]);
  await stop(page);

  for (const [track, expected] of [["rh", 65], ["lh", 41]]) {
    await clearSent(page);
    await page.locator(`#track-${track}`).click();
    assert.match(await page.locator("#timbre-basic").getAttribute("class"), /active/);
    await page.locator("#btn-play").click();
    await waitForSound(page);
    assert.deepEqual(await onsets(page), [expected]);
    await stop(page);
  }

  await page.locator("#timbre-warm").click();
  await page.waitForFunction(() => window.audioChecks.at(-1).context.state === "closed");
  assert.equal(await page.locator("#reverb-slider").isEnabled(), true);
  await page.locator("#timbre-basic").click();
  await page.locator("#btn-reset").click();
  assert.equal(await page.locator("#cur-measure").innerText(), "1");
  assert.match(await page.locator("#timbre-basic").getAttribute("class"), /active/);
  console.log(JSON.stringify({ bothHandChannelRms: both, sampleRate: await page.evaluate(() => window.audioChecks[0].context.sampleRate) }));
});

test("stopping pending WASM startup cannot play later; failed loading is visible and retry works", { timeout: 45000 }, async t => {
  const page = await newScore(t);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let sawRequest;
  const requested = new Promise(resolve => { sawRequest = resolve; });
  await page.route("**/moonlight_wasm.wasm", async route => {
    sawRequest();
    await gate;
    await route.continue();
  });
  await page.locator("#btn-play").click();
  await requested;
  await page.locator("#btn-stop").click();
  release();
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(() => window.audioChecks.length), 0);
  assert.equal(await page.evaluate(() => window.scoreContexts[0].state), "closed");
  assert.match(await page.locator("#btn-play").innerText(), /播放/);
  await page.unroute("**/moonlight_wasm.wasm");
  await page.route("**/moonlight_wasm.wasm", route => route.fulfill({ status: 503, body: "unavailable" }));
  await page.locator("#btn-play").click();
  await page.waitForFunction(() => document.querySelector("#engine-status").textContent.includes("加载失败"));
  assert.match(await page.locator("#timbre-basic").getAttribute("class"), /active/);
  assert.match(await page.locator("#btn-play").innerText(), /播放/);
  await page.unroute("**/moonlight_wasm.wasm");
  await page.locator("#btn-play").click();
  await waitForSound(page);
  await stop(page);
});
