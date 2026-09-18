import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("AudioWorklet process crosses JS/WASM exactly once per quantum", async () => {
  const source = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  const processBody = source.slice(source.indexOf("  process(_inputs, outputs)"), source.indexOf("  fail(message)"));
  const calls = processBody.match(/moonlight_process_block\(/g) ?? [];
  assert.equal(calls.length, 1);
});

test("AudioWorklet render path avoids parsing, allocation syntax, and logging", async () => {
  const source = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  const processBody = source.slice(source.indexOf("  process(_inputs, outputs)"), source.indexOf("  fail(message)"));
  for (const forbidden of ["JSON.parse", "console.", "new Array", "new Float32Array", "new Uint8Array", "new DataView"]) {
    assert.equal(processBody.includes(forbidden), false, forbidden);
  }
});

test("worklet exposes deadline, memory, block-size and underrun telemetry", async () => {
  const source = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  for (const field of ["blockSize", "deadlineRatio", "memoryBytes", "underruns", "lateEvents"]) {
    assert.equal(source.includes(field), true, field);
  }
});


test("physical engine start waits for the AudioWorklet ready message and rejects initialization errors", async (t) => {
  const { PhysicalC4WorkletEngine } = await import("../../lib/audio/physical-c4-worklet-engine.ts");

  const originalNode = globalThis.AudioWorkletNode;
  const originalFetch = globalThis.fetch;

  class FakeAudioWorkletNode {
    static instances = [];

    constructor() {
      this.port = {
        onmessage: null,
        postMessage() {},
      };
      this.onprocessorerror = null;
      FakeAudioWorkletNode.instances.push(this);
    }

    connect() {
      return this;
    }

    disconnect() {}
  }

  function makeContext() {
    return {
      state: "running",
      sampleRate: 48_000,
      currentTime: 1,
      baseLatency: 0.01,
      outputLatency: 0.02,
      destination: {},
      audioWorklet: {
        async addModule() {},
      },
      createGain() {
        return {
          gain: { value: 0 },
          connect() {
            return this;
          },
          disconnect() {},
        };
      },
      async resume() {
        this.state = "running";
      },
      async suspend() {
        this.state = "suspended";
      },
      async close() {
        this.state = "closed";
      },
    };
  }

  globalThis.AudioWorkletNode = FakeAudioWorkletNode;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    async arrayBuffer() {
      return new ArrayBuffer(8);
    },
  });

  t.after(() => {
    if (originalNode === undefined) delete globalThis.AudioWorkletNode;
    else globalThis.AudioWorkletNode = originalNode;
    globalThis.fetch = originalFetch;
  });

  const context = makeContext();
  const engine = new PhysicalC4WorkletEngine({ context, ownsContext: false });
  let resolved = false;
  const started = engine.start().then(() => {
    resolved = true;
  });

  while (FakeAudioWorkletNode.instances.length === 0) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(resolved, false);
  assert.equal(engine.snapshot().ready, false);

  FakeAudioWorkletNode.instances[0].port.onmessage({
    data: { type: "ready", memoryBytes: 65_536 },
  });
  await started;
  assert.equal(resolved, true);
  assert.equal(engine.snapshot().ready, true);
  assert.equal(engine.snapshot().parameters.wasmMemoryBytes, 65_536);

  const failedEngine = new PhysicalC4WorkletEngine({
    context: makeContext(),
    ownsContext: false,
  });
  const failedStart = failedEngine.start();

  while (FakeAudioWorkletNode.instances.length < 2) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  FakeAudioWorkletNode.instances[1].port.onmessage({
    data: { type: "error", message: "wasm init failed" },
  });

  await assert.rejects(failedStart, /wasm init failed/);
  assert.equal(failedEngine.snapshot().ready, false);
  assert.equal(failedEngine.snapshot().state, "error");
  assert.equal(failedEngine.snapshot().lastError, "wasm init failed");
});


test("disposing during startup rejects the pending start and ignores a late ready message", async (t) => {
  const { PhysicalC4WorkletEngine } = await import("../../lib/audio/physical-c4-worklet-engine.ts");

  const originalNode = globalThis.AudioWorkletNode;
  const originalFetch = globalThis.fetch;

  class FakeAudioWorkletNode {
    static instances = [];

    constructor() {
      this.port = {
        onmessage: null,
        postMessage() {},
      };
      this.onprocessorerror = null;
      FakeAudioWorkletNode.instances.push(this);
    }

    connect() {
      return this;
    }

    disconnect() {}
  }

  const context = {
    state: "running",
    sampleRate: 48_000,
    currentTime: 1,
    baseLatency: 0.01,
    outputLatency: 0.02,
    destination: {},
    audioWorklet: {
      async addModule() {},
    },
    createGain() {
      return {
        gain: { value: 0 },
        connect() {
          return this;
        },
        disconnect() {},
      };
    },
    async resume() {},
    async suspend() {},
    async close() {
      this.state = "closed";
    },
  };

  globalThis.AudioWorkletNode = FakeAudioWorkletNode;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    async arrayBuffer() {
      return new ArrayBuffer(8);
    },
  });

  t.after(() => {
    if (originalNode === undefined) delete globalThis.AudioWorkletNode;
    else globalThis.AudioWorkletNode = originalNode;
    globalThis.fetch = originalFetch;
  });

  const engine = new PhysicalC4WorkletEngine({ context, ownsContext: false });
  const started = engine.start();

  while (FakeAudioWorkletNode.instances.length === 0) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  const node = FakeAudioWorkletNode.instances[0];

  await engine.dispose();
  await assert.rejects(started, /disposed during startup/);
  assert.equal(engine.snapshot().state, "disposed");
  assert.equal(engine.snapshot().ready, false);

  node.port.onmessage({
    data: { type: "ready", memoryBytes: 65_536 },
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(engine.snapshot().state, "disposed");
  assert.equal(engine.snapshot().ready, false);
});
