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
  mode?: "c4" | "basic";
};

type WorkletMessage =
  | { type: "ready"; memoryBytes: number }
  | { type: "telemetry"; blockSize: number; deadlineRatio: number; memoryBytes: number; underruns: number; lateEvents: number; overflowEvents: number; activeVoices: number }
  | { type: "error"; message: string };

export class PhysicalC4WorkletEngine implements SoundEngine {
  readonly id: string;
  readonly label: string;

  private contextValue: AudioContext | null;
  private readonly ownsContext: boolean;
  private readonly mode: "c4" | "basic";
  private readonly sources = new Map<string, number>();
  private readonly pressed = new Map<number, number>();
  private sustain = 0;
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
  private telemetry = { blockSize: 0, deadlineRatio: 0, memoryBytes: 0, underruns: 0, lateEvents: 0, overflowEvents: 0 };

  constructor(options: Options = {}) {
    this.mode = options.mode ?? "c4";
    this.id = this.mode === "basic" ? "basic-piano" : "physical-c4";
    this.label = this.mode === "basic" ? "Rust 基础全键盘" : "Rust 物理 C4";
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
    this.assertUsable();
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
      if (event.type === "note-on" || event.type === "note-off") {
        if (this.mode === "c4" && event.note !== 60) throw new RangeError("The physical tracer currently supports C4 (MIDI 60) only.");
        if (this.mode === "basic" && (event.note < 21 || event.note > 108)) throw new RangeError("The basic piano supports MIDI 21–108.");
      } else if (event.type === "sustain" && this.mode === "basic") {
        // The current basic model has a binary damper: positions below 0.5 are up.
      } else if (event.type === "sustain" || event.type === "sostenuto" || event.type === "una-corda") {
        throw new Error(`${event.type} is not yet supported by ${this.label}.`);
      }
    }

    for (const event of batch) {
      this.lastEventType = event.type;
      if (event.type === "sustain") {
        const frame = !event.time || event.time.kind === "now"
          ? Math.max(Math.round(context.currentTime * context.sampleRate), clock.currentSampleFrame + leadFrames)
          : Math.round(resolveEventTimeSeconds(event.time, clock) * context.sampleRate);
        node.port.postMessage({ type: "event", frame, kind: 4, note: 0, value: event.position });
        this.sustain = event.position >= 0.5 ? 1 : 0;
        continue;
      }
      if (event.type !== "note-on" && event.type !== "note-off") continue;
      if (this.mode === "basic") {
        if (event.type === "note-on") {
          if (this.sources.has(event.sourceId)) continue;
          this.sources.set(event.sourceId, event.note);
          this.pressed.set(event.note, (this.pressed.get(event.note) ?? 0) + 1);
        } else {
          if (this.sources.get(event.sourceId) !== event.note) continue;
          this.sources.delete(event.sourceId);
          const remaining = (this.pressed.get(event.note) ?? 1) - 1;
          if (remaining > 0) {
            this.pressed.set(event.note, remaining);
            continue;
          }
          this.pressed.delete(event.note);
        }
      }
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
      this.activeVoices = this.mode === "basic" ? this.pressed.size : event.type === "note-on" ? 1 : 0;
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
    this.sources.clear();
    this.pressed.clear();
    this.sustain = 0;
    this.activeVoices = 0;
    this.emit();
  }

  async handleRouteChange() {
    this.routeVersion += 1;
    this.emit();
  }

  async dispose() {
    if (this.stateValue === "disposed") return;

    this.stateValue = "disposed";
    const rejectInitialization = this.rejectPendingInitialization;
    this.rejectPendingInitialization = null;
    rejectInitialization?.(new Error("Sound engine was disposed during startup."));

    this.stopAll();
    const node = this.node;
    const master = this.master;
    if (node || master) this.releaseWorkletGraph(node, master);

    const context = this.contextValue;
    this.contextValue = null;
    this.ready = false;
    this.activeVoices = 0;
    this.emit();
    this.listeners.clear();

    if (context && this.ownsContext && context.state !== "closed") await context.close();
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
      profile: this.mode === "basic" ? "analytic-basic-piano-worklet" : "physical-c4-worklet",
      activeVoices: this.activeVoices,
      pedals: { sustain: this.sustain, sostenuto: 0, unaCorda: 0 },
      parameters: {
        blockSize: this.telemetry.blockSize,
        renderDeadlineRatio: this.telemetry.deadlineRatio,
        wasmMemoryBytes: this.telemetry.memoryBytes,
        underruns: this.telemetry.underruns,
        lateEvents: this.telemetry.lateEvents,
        overflowEvents: this.telemetry.overflowEvents,
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

      const createdNode = new AudioWorkletNode(context, this.mode === "basic" ? "moonlight-basic-piano" : "moonlight-physical-c4", {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [this.mode === "basic" ? 2 : 1],
        processorOptions: { wasmBytes, mode: this.mode },
      });
      const createdMaster = context.createGain();
      node = createdNode;
      master = createdMaster;
      // Lab calibration is intentionally outside the Rust model so A/B loudness can be adjusted
      // without changing the physical state or offline-reference numerics.
      createdMaster.gain.value = 1.0;
      createdNode.connect(createdMaster).connect(context.destination);
      this.node = createdNode;
      this.master = createdMaster;

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
          && this.node === createdNode
          && this.contextValue === context
        );

        const failInitialization = (message: string) => {
          if (!isCurrentInitialization()) {
            this.releaseWorkletGraph(createdNode, createdMaster);
            rejectOnce(new Error("Sound engine was disposed during startup."));
            return;
          }
          this.ready = false;
          this.releaseWorkletGraph(createdNode, createdMaster);
          this.stateValue = "error";
          this.lastError = message;
          this.emit();
          rejectOnce(new Error(message));
        };

        createdNode.port.onmessage = (event: MessageEvent<WorkletMessage>) => {
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
            this.activeVoices = message.activeVoices;
            this.emit();
            return;
          }
          failInitialization(message.message);
        };

        createdNode.onprocessorerror = () => {
          failInitialization("AudioWorklet processor failed.");
        };
      });

      await waitFor(ready);
    } catch (error) {
      if (node || master) this.releaseWorkletGraph(node, master);
      this.ready = false;
      throw error;
    } finally {
      if (this.rejectPendingInitialization === cancelInitialization) {
        this.rejectPendingInitialization = null;
      }
    }
  }

  private releaseWorkletGraph(node: AudioWorkletNode | null, master: GainNode | null) {
    if (node) {
      node.port.onmessage = null;
      node.onprocessorerror = null;
      try {
        node.disconnect();
      } catch {
        // The graph may already have been disconnected by another lifecycle path.
      }
      if (this.node === node) this.node = null;
    }
    if (master) {
      try {
        master.disconnect();
      } catch {
        // The graph may already have been disconnected by another lifecycle path.
      }
      if (this.master === master) this.master = null;
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
