import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
let browser;
let server;
let origin;

before(async () => {
  server = createServer(async (request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    if (pathname === "/") {
      response.writeHead(200, { "Content-Type": "text/html" }).end('<!doctype html><button id="start">Start audio</button>');
      return;
    }
    if (!/^\/audio\/[\w.-]+$/.test(pathname)) {
      response.writeHead(404).end();
      return;
    }
    try {
      const content = await readFile(path.join(root, "public", pathname));
      response.writeHead(200, { "Content-Type": pathname.endsWith(".wasm") ? "application/wasm" : "text/javascript" }).end(content);
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true, executablePath: process.env.PIANO_CHROMIUM_PATH || undefined });
});

after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

for (const sampleRate of [44_100, 48_000]) {
  test(`real AudioWorklet renders nonlinear C4 and reports contact at ${sampleRate} Hz`, { timeout: 30000 }, async t => {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    t.after(async () => { await page.close(); assert.deepEqual(errors, []); });
    await page.goto(origin);
    await page.evaluate(async rate => {
      const { PhysicalC4WorkletEngine } = await import("/audio/physical-c4-worklet-engine.js");
      const OriginalNode = window.AudioWorkletNode;
      window.AudioWorkletNode = new Proxy(OriginalNode, {
        construct(target, args) {
          const node = Reflect.construct(target, args);
          window.hammerAnalyser = args[0].createAnalyser();
          node.connect(window.hammerAnalyser);
          return node;
        },
      });
      const context = new AudioContext({ sampleRate: rate });
      window.hammerEngine = new PhysicalC4WorkletEngine({ context, ownsContext: true });
      document.querySelector("#start").onclick = async () => {
        try { await window.hammerEngine.start(); }
        catch (error) { window.hammerError = String(error); }
      };
    }, sampleRate);
    await page.click("#start");
    await page.waitForFunction(() => window.hammerEngine.snapshot().ready || window.hammerError);
    assert.equal(await page.evaluate(() => window.hammerError), undefined);

    async function strike(velocity, previousSpeed = 0) {
      await page.evaluate(value => {
        const engine = window.hammerEngine;
        engine.stopAll();
        engine.dispatch({ type: "note-on", sourceId: "browser-hammer", note: 60,
          velocity: value, time: { kind: "audio-time", seconds: engine.clock().currentTimeSeconds + 0.05 } });
      }, velocity);
      await page.waitForFunction(speed => {
        const p = window.hammerEngine.snapshot().parameters;
        return p.hammerInitialVelocityMps > speed && p.hammerContactMs > 0;
      }, previousSpeed);
      return page.evaluate(() => {
        const analyser = window.hammerAnalyser;
        const samples = new Float32Array(analyser.fftSize);
        analyser.getFloatTimeDomainData(samples);
        return { ...window.hammerEngine.snapshot().parameters,
          sampleRate: window.hammerEngine.clock().sampleRate,
          rms: Math.sqrt(samples.reduce((sum, x) => sum + x * x, 0) / samples.length),
          finite: samples.every(Number.isFinite) };
      });
    }
    const weak = await strike(0.2);
    const strong = await strike(0.9, weak.hammerInitialVelocityMps);
    assert.equal(strong.sampleRate, sampleRate);
    assert.ok(weak.finite && strong.finite);
    assert.ok(weak.rms > 0 && strong.rms > weak.rms);
    assert.ok(strong.hammerPeakForceNewtons > weak.hammerPeakForceNewtons);
    assert.ok(strong.hammerContactMs < weak.hammerContactMs);
    assert.ok(strong.hammerMaxEnergyErrorJoules < 1e-7);
    assert.equal(strong.overflowEvents, 0);
    await page.evaluate(() => window.hammerEngine.stopAll());
    await page.waitForFunction(() => window.hammerEngine.snapshot().parameters.hammerInputEnergyJoules === 0);
    assert.equal(await page.evaluate(() => {
      const samples = new Float32Array(window.hammerAnalyser.fftSize);
      window.hammerAnalyser.getFloatTimeDomainData(samples);
      return samples.every(value => value === 0);
    }), true);
    await page.evaluate(() => window.hammerEngine.dispose());
    console.log(JSON.stringify({ sampleRate, weak, strong }));
  });
}
