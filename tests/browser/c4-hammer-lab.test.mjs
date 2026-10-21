import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import { chromium } from "playwright";

const root = path.resolve(import.meta.dirname, "../..");

test("the full C4 lab sweep pauses beyond the timing probe and cancels cleanly", { timeout: 60000 }, async t => {
  let origin = process.env.PIANO_LAB_URL;
  let server;
  if (!origin) {
    const reservation = createServer();
    await new Promise(resolve => reservation.listen(0, "127.0.0.1", resolve));
    const port = reservation.address().port;
    await new Promise(resolve => reservation.close(resolve));
    origin = `http://127.0.0.1:${port}`;
    server = spawn(process.execPath, ["node_modules/vinext/dist/cli.js", "start", "--port", String(port)], {
      cwd: root,
      env: { ...process.env, WRANGLER_LOG_PATH: "work/lab-test-wrangler.log" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    server.stdout.on("data", chunk => { output = (output + chunk).slice(-4000); });
    server.stderr.on("data", chunk => { output = (output + chunk).slice(-4000); });
    t.after(() => { server.kill("SIGTERM"); });
    const deadline = Date.now() + 20000;
    for (;;) {
      if (server.exitCode !== null) throw new Error(`Production lab exited: ${output}`);
      try { if ((await fetch(`${origin}/lab/engine`)).ok) break; } catch { /* Server is starting. */ }
      if (Date.now() >= deadline) throw new Error(`Build the production app before this test: ${output}`);
      await delay(100);
    }
  }

  const browser = await chromium.launch({ headless: true, executablePath: process.env.PIANO_CHROMIUM_PATH || undefined });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.goto(`${origin}/lab/engine`);
  await page.getByRole("combobox").selectOption("physical-c4");
  await page.getByRole("button", { name: "启动", exact: true }).click();
  const value = label => page.getByText(label, { exact: true }).locator("..").locator("dd");
  const waitValue = (label, expected) => page.waitForFunction(({ label, expected }) => {
    const field = Array.from(document.querySelectorAll("dt")).find(node => node.textContent === label);
    return field?.nextElementSibling?.textContent === expected;
  }, { label, expected });
  await waitValue("就绪", "是");
  await page.getByRole("button", { name: "扫描 127 档力度" }).click();

  // The original eight-beat timing probe completes well before the 32-second
  // sweep. Pause must still freeze the actual audio sample clock afterward.
  await waitValue("Transport", "completed");
  assert.match(await page.locator('[aria-live="polite"]').innerText(), /扫描 \d+\/127/);
  await page.getByRole("button", { name: "暂停/继续" }).click();
  await waitValue("状态", "suspended");
  const pausedFrame = Number(await value("sample frame").innerText());
  const pausedProgress = await page.locator('[aria-live="polite"]').innerText();
  await delay(600);
  assert.equal(Number(await value("sample frame").innerText()), pausedFrame);
  assert.equal(await page.locator('[aria-live="polite"]').innerText(), pausedProgress);

  await page.getByRole("button", { name: "暂停/继续" }).click();
  await waitValue("状态", "running");
  await page.waitForFunction(frame => {
    const field = Array.from(document.querySelectorAll("dt")).find(node => node.textContent === "sample frame");
    return Number(field?.nextElementSibling?.textContent) > frame;
  }, pausedFrame);
  await page.getByRole("button", { name: "停止试听", exact: true }).click();
  await waitValue("累计输入能量", "0.000e+0 J");
  assert.equal(await value("queue overflow").innerText(), "0");
  assert.equal(await page.getByRole("button", { name: "扫描 127 档力度" }).isEnabled(), true);

  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true,
    "contact diagnostics and velocity controls must fit a phone viewport");

  // Switching back preserves the accepted default engine's controls.
  await page.getByRole("combobox").selectOption("basic-piano");
  await waitValue("就绪", "是");
  assert.equal(await page.getByRole("heading", { name: "C4 琴槌与力度" }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "C 大三和弦", exact: true }).isEnabled(), true);
  await page.getByRole("button", { name: "停止", exact: true }).click();
  await waitValue("就绪", "否");
  assert.deepEqual(pageErrors, []);
  console.log(JSON.stringify({ pausedFrame, pausedProgress, longSweepPauseVerified: true }));
});
