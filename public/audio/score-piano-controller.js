// A static-score bridge to the application's shared SoundEngine host adapter.
(() => {
  const assetRoot = new URL("./", document.currentScript.src);

  class BasicScorePiano {
    constructor(options = {}) {
      this.assetRoot = options.assetRoot ?? assetRoot;
      this.loadEngine = options.loadEngine ?? (() => import(new URL("physical-c4-worklet-engine.js", this.assetRoot).href));
      this.createContext = options.createContext ?? (() => {
        const Context = window.AudioContext || window.webkitAudioContext;
        return new Context({ latencyHint: "interactive" });
      });
      this.context = null;
      this.engine = null;
      this.starting = null;
      this.generation = 0;
      this.serial = 0;
    }

    async start() {
      if (this.starting) return this.starting;
      if (this.engine) {
        await this.engine.start();
        return this;
      }
      const generation = ++this.generation;
      const context = this.createContext();
      this.context = context;
      // Resume in the click handler, before loading any modules or WASM.
      const resumed = context.resume();
      const assertCurrent = () => {
        if (generation !== this.generation) throw new Error("Score audio startup was cancelled.");
      };
      let engine = null;
      const starting = (async () => {
        try {
          await resumed;
          const { PhysicalC4WorkletEngine } = await this.loadEngine();
          assertCurrent();
          engine = new PhysicalC4WorkletEngine({
            context, ownsContext: true, mode: "basic",
            wasmUrl: new URL("moonlight_wasm.wasm", this.assetRoot).href,
            workletUrl: new URL("physical-c4-worklet.js", this.assetRoot).href,
          });
          this.engine = engine;
          await engine.start();
          assertCurrent();
          return this;
        } catch (error) {
          if (generation === this.generation) {
            this.engine = null;
            this.context = null;
            if (engine) await engine.dispose();
            else if (context.state !== "closed") await context.close();
          }
          throw error;
        } finally {
          if (this.starting === starting) this.starting = null;
        }
      })();
      this.starting = starting;
      return starting;
    }

    playNote(pitch, durationSeconds, volume = 0.44, hand = "rh", when = 0) {
      const engine = this.engine;
      if (!engine?.snapshot().ready) throw new Error("Score piano is not ready.");
      const match = /^([A-G])([#b]?)(-?\d+)$/.exec(pitch);
      if (!match) throw new RangeError(`Invalid pitch: ${pitch}`);
      const semitone = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }[match[1]];
      const note = (Number(match[3]) + 1) * 12 + semitone + (match[2] === "#" ? 1 : match[2] === "b" ? -1 : 0);
      const sourceId = `score-${hand}-${++this.serial}`;
      const start = when > 0 ? when : engine.clock().currentTimeSeconds + 0.02;
      engine.dispatch([
        { type: "note-on", sourceId, note,
          velocity: Math.min(1, Math.max(0.01, volume * 1.6 * (hand === "lh" ? 0.92 : 1))),
          time: when > 0 ? { kind: "audio-time", seconds: start } : { kind: "now" } },
        { type: "note-off", sourceId, note, releaseVelocity: 0.5,
          time: { kind: "audio-time", seconds: start + Math.max(0.01, durationSeconds) } },
      ]);
    }

    stopAll() {
      if (this.starting) void this.dispose();
      else this.engine?.stopAll({ kind: "now" });
    }

    async dispose() {
      ++this.generation;
      const engine = this.engine;
      const context = this.context;
      this.engine = null;
      this.context = null;
      this.starting = null;
      if (engine) await engine.dispose();
      else if (context && context.state !== "closed") await context.close();
    }
  }

  globalThis.BasicScorePiano = BasicScorePiano;
})();
