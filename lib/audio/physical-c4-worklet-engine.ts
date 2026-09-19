import {
  resolveEventTimeSeconds,
  validateSoundEngineEvent,
  type SoundEngine,
  type SoundEngineClock,
  type SoundEngineEvent,
  type SoundEngineListener,
  type SoundEngineSnapshot,
  type SoundEngineState,
  type SoundEventTime,
} from "./sound-engine.ts";

type Options = {
  context?: AudioContext;
  ownsContext?: boolean;
};

type WorkletMessage =
  | { type: "ready"; memoryBytes: number }
  | { type: "telemetry"; blockSize: number; deadlineRatio: number; memoryBytes: number; underruns: number; lateEvents: number }
  | { type: "error"; message: string };

export class PhysicalC4WorkletEngine implements SoundEngine {
  readonly id = "physical-c4";
  readonly label = "Rust 物理 C4";

  private contextValue: AudioContext | null;
  private readonly ownsContext: boolean;
  private node: AudioWorkletNode | null = null;
  private master: GainNode | null = null;
  private stateValue: SoundEngineState = "idle";
  private listeners = new Set<SoundEngineListener>();
  private lastEventType: SoundEngineEvent["type"] | null = null;
  private lastError: string | null = null;
  private routeVersion = 0;
  private ready = false;
  private initializationPromise: Promise<void> | null = null;
  private rejectPendingInitialization: ((error: Error) => void) | null = null;
  private activeVoices = 0;
  private telemetry = { blockSize: 0, deadlineRatio: 0, memoryBytes: 0, underruns: 0, lateEvents: 0 };

  constructor(options: Options = {}) {
    this.contextValue = options.context ?? null;
    this.ownsContext = options.ownsContext ?? options.context === undefined;
  }

  async start() {
    this.assertUsable();
    this.stateValue = "starting";
    this.emit();
    try {
      const context = this.ensureContext();
      if (!this.ready) await this.ensureWorkletReady(context);
      if (context.state === "suspended") await context.resume();
      this.stateValue = context.state === "running" ? "running" : "suspended";
      this.lastError = null;
    } catch (error) {
      if (!this.isDisposed()) {
        this.stateValue = "error";
        this.lastError = errorMessage(error);
        this.emit();
      }
      throw error;
    }
    this.emit();
  }

  async resume() {
    const context = this.ensureContext();
    try {
      if (context.state === "suspended") await context.resume();
      this.stateValue = context.state === "running" ? "running" : "suspended";
      this.lastError = null;
    } catch (error) {
      this.stateValue = "error";
      this.lastError = errorMessage(error);
    }
    this.emit();
  }

  async suspend() {
    const context = this.contextValue;
    if (!context || context.state === "closed") return;
    try {
      if (context.state === "running") await context.suspend();
      this.stateValue = "suspended";
    } catch (error) {
      this.lastError = errorMessage(error);
      this.stateValue = "error";
    }
    this.emit();
  }

  dispatch(events: SoundEngineEvent | readonly SoundEngineEvent[]) {
    this.assertUsable();
    const node = this.node;
    const context = this.ensureContext();
    if (!node || !this.ready) throw new Error("Rust physical C4 WASM is not ready.");
    const batch = Array.isArray(events) ? events : [events];
    const clock = this.clock();
    const leadFrames = 256;

    for (const event of batch) {
      validateSoundEngineEvent(event);
      this.lastEventType = event.type;
      if (event.type !== "note-on" && event.type !== "note-off") continue;
      if (event.note !== 60) throw new RangeError("The physical tracer currently supports C4 (MIDI 60) only.");
      let frame = Math.round(resolveEventTimeSeconds(event.time, clock) * context.sampleRate);
      if (!event.time || event.time.kind === "now") {
        frame = Math.max(frame, clock.currentSampleFrame + leadFrames);
      }
      node.port.postMessage({
        type: "event",
        frame,
        kind: event.type === "note-on" ? 1 : 2,
        note: event.note,
        value: event.type === "note-on" ? event.velocity : event.releaseVelocity,
      });
      this.activeVoices = event.type === "note-on" ? 1 : 0;
    }
    this.emit();
  }

  stopAll(time?: SoundEventTime) {
    if (!this.node) return;
    const clock = this.clock();
    const frame = time
      ? Math.round(resolveEventTimeSeconds(time, clock) * Math.max(clock.sampleRate, 1))
      : clock.currentSampleFrame + 128;
    this.node.port.postMessage({ type: "reset", frame });
    this.activeVoices = 0;
    this.emit();
  }

  async handleRouteChange() {
    this.routeVersion += 1;
    this.emit();
  }

  async dispose() {
    if (this.stateValue === "disposed") return;
    const rejectInitialization = this.rejectPendingInitialization;
    this.rejectPendingInitialization = null;
    rejectInitialization?.(new Error("Sound engine was disposed during startup."));
    this.stopAll();
    this.node?.disconnect();
    this.master?.disconnect();
    this.node = null;
    this.master = null;
    const context = this.contextValue;
    if (context && this.ownsContext && context.state !== "closed") await context.close();
    this.contextValue = null;
    this.ready = false;
    this.stateValue = "disposed";
    this.emit();
    this.listeners.clear();
  }

  clock(): SoundEngineClock {
    const context = this.contextValue;
    if (!context) return {
      sampleRate: 0, currentTimeSeconds: 0, currentSampleFrame: 0,
      state: "unavailable", baseLatencySeconds: null, outputLatencySeconds: null,
    };
    const outputLatency = "outputLatency" in context
      ? (context as AudioContext & { outputLatency?: number }).outputLatency ?? null
      : null;
    return {
      sampleRate: context.sampleRate,
      currentTimeSeconds: context.currentTime,
      currentSampleFrame: Math.floor(context.currentTime * context.sampleRate),
      state: context.state,
      baseLatencySeconds: Number.isFinite(context.baseLatency) ? context.baseLatency : null,
      outputLatencySeconds: outputLatency !== null && Number.isFinite(outputLatency) ? outputLatency : null,
    };
  }

  snapshot(): SoundEngineSnapshot {
    return {
      id: this.id,
      label: this.label,
      state: this.stateValue,
      ready: this.ready,
      profile: "physical-c4-worklet",
      activeVoices: this.activeVoices,
      pedals: { sustain: 0, sostenuto: 0, unaCorda: 0 },
      parameters: {
        blockSize: this.telemetry.blockSize,
        renderDeadlineRatio: this.telemetry.deadlineRatio,
        wasmMemoryBytes: this.telemetry.memoryBytes,
        underruns: this.telemetry.underruns,
        lateEvents: this.telemetry.lateEvents,
      },
      clock: this.clock(),
      routeVersion: this.routeVersion,
      lastEventType: this.lastEventType,
      lastError: this.lastError,
    };
  }

  subscribe(listener: SoundEngineListener) {
    this.listeners.add(listener);
    listener(this.snapshot());
    return () => this.listeners.delete(listener);
  }

  private ensureContext() {
    if (this.contextValue) return this.contextValue;
    if (typeof window === "undefined" || !window.AudioContext) throw new Error("Web Audio is unavailable.");
    this.contextValue = new window.AudioContext({ latencyHint: "interactive" });
    return this.contextValue;
  }

  private ensureWorkletReady(context: AudioContext) {
    if (this.ready) return Promise.resolve();
    if (this.initializationPromise) return this.initializationPromise;

    const pending = this.initializeWorklet(context);
    const tracked = pending.finally(() => {
      if (this.initializationPromise === tracked) {
        this.initializationPromise = null;
      }
    });
    this.initializationPromise = tracked;
    return tracked;
  }

  private async initializeWorklet(context: AudioContext) {
    if (!context.audioWorklet || typeof AudioWorkletNode === "undefined") {
      throw new Error("AudioWorklet is unavailable in this browser.");
    }

    let rejectCancellation: ((error: Error) => void) | null = null;
    let cancelled = false;
    const cancellation = new Promise<never>((_resolve, reject) => {
      rejectCancellation = reject;
    });
    const cancelInitialization = (error: Error) => {
      if (cancelled) return;
      cancelled = true;
      rejectCancellation?.(error);
    };
    const waitFor = <T>(operation: Promise<T>) => Promise.race([operation, cancellation]);
    const assertCurrent = () => {
      if (this.isDisposed() || this.contextValue !== context) {
        throw new Error("Sound engine was disposed during startup.");
      }
    };

    this.rejectPendingInitialization = cancelInitialization;

    let node: AudioWorkletNode | null = null;
    let master: GainNode | null = null;

    try {
      const response = await waitFor(fetch("/audio/moonlight_wasm.wasm", { cache: "no-store" }));
      assertCurrent();
      if (!response.ok) {
        throw new Error(`Rust WASM unavailable (HTTP ${response.status}). Run npm run audio:wasm first.`);
      }

      const wasmBytes = await waitFor(response.arrayBuffer());
      assertCurrent();

      await waitFor(context.audioWorklet.addModule("/audio/physical-c4-worklet.js"));
      assertCurrent();

      node = new AudioWorkletNode(context, "moonlight-physical-c4", {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        processorOptions: { wasmBytes },
      });
      master = context.createGain();
      // Lab calibration is intentionally outside the Rust model so A/B loudness can be adjusted
      // without changing the physical state or offline-reference numerics.
      master.gain.value = 1.0;
      node.connect(master).connect(context.destination);
      this.node = node;
      this.master = master;

      const ready = new Promise<void>((resolve, reject) => {
        let settled = false;

        const resolveOnce = () => {
          if (settled) return;
          settled = true;
          resolve();
        };

        const rejectOnce = (error: Error) => {
          if (settled) return;
          settled = true;
          reject(error);
        };

        const isCurrentInitialization = () => (
          !this.isDisposed()
          && this.node === node
          && this.contextValue === context
        );

        const failInitialization = (message: string) => {
          if (!isCurrentInitialization()) {
            rejectOnce(new Error("Sound engine was disposed during startup."));
            return;
          }
          this.ready = false;
          this.stateValue = "error";
          this.lastError = message;
          this.emit();
          rejectOnce(new Error(message));
        };

        node.port.onmessage = (event: MessageEvent<WorkletMessage>) => {
          const message = event.data;
          if (message.type === "ready") {
            if (!isCurrentInitialization()) {
              rejectOnce(new Error("Sound engine was disposed during startup."));
              return;
            }
            this.ready = true;
            this.telemetry.memoryBytes = message.memoryBytes;
            this.stateValue = context.state === "running" ? "running" : "suspended";
            this.lastError = null;
            this.emit();
            resolveOnce();
            return;
          }
          if (message.type === "telemetry") {
            if (!isCurrentInitialization()) return;
            this.telemetry = message;
            this.emit();
            return;
          }
          failInitialization(message.message);
        };

        node.onprocessorerror = () => {
          failInitialization("AudioWorklet processor failed.");
        };
      });

      await waitFor(ready);
    } catch (error) {
      if (node) {
        node.port.onmessage = null;
        node.onprocessorerror = null;
        try {
          node.disconnect();
        } catch {
          // The graph may already have been disconnected by dispose().
        }
      }
      if (master) {
        try {
          master.disconnect();
        } catch {
          // The graph may already have been disconnected by dispose().
        }
      }
      if (this.node === node) this.node = null;
      if (this.master === master) this.master = null;
      this.ready = false;
      throw error;
    } finally {
      if (this.rejectPendingInitialization === cancelInitialization) {
        this.rejectPendingInitialization = null;
      }
    }
  }

  private isDisposed() {
    return this.stateValue === "disposed";
  }

  private assertUsable() {
    if (this.isDisposed() || this.stateValue === "closed") throw new Error("Sound engine is disposed.");
  }

  private emit() {
    const snapshot = this.snapshot();
    for (const listener of this.listeners) listener(snapshot);
  }
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
