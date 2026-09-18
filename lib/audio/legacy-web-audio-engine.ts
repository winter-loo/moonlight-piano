import { midiToFrequency } from "../music/pitch.ts";
import {
  resolveEventTimeSeconds,
  validateSoundEngineEvent,
  type MetronomeEvent,
  type NoteOffEvent,
  type NoteOnEvent,
  type ParameterEvent,
  type PedalEvent,
  type SoundEngine,
  type SoundEngineClock,
  type SoundEngineEvent,
  type SoundEngineListener,
  type SoundEnginePedals,
  type SoundEngineSnapshot,
  type SoundEngineState,
  type SoundEventTime,
} from "./sound-engine.ts";

export type LegacyWebAudioProfile = "lesson-tone" | "interactive-piano";

type LegacyWebAudioEngineOptions = {
  id: string;
  label: string;
  profile: LegacyWebAudioProfile;
  context?: AudioContext;
  ownsContext?: boolean;
};

type LegacyVoice = {
  sourceId: string;
  note: number;
  gain: GainNode;
  oscillators: OscillatorNode[];
  sustainLevel: number;
  released: boolean;
  capturedBySostenuto: boolean;
  releaseScheduledAt: number | null;
};

const DEFAULT_PEDALS: SoundEnginePedals = Object.freeze({
  sustain: 0,
  sostenuto: 0,
  unaCorda: 0,
});

export class LegacyWebAudioEngine implements SoundEngine {
  readonly id: string;
  readonly label: string;

  private readonly profile: LegacyWebAudioProfile;
  private readonly ownsContext: boolean;
  private contextValue: AudioContext | null;
  private masterGain: GainNode | null = null;
  private compressor: DynamicsCompressorNode | null = null;
  private stateValue: SoundEngineState = "idle";
  private readonly voices = new Map<string, LegacyVoice>();
  private readonly listeners = new Set<SoundEngineListener>();
  private pedalsValue: SoundEnginePedals = { ...DEFAULT_PEDALS };
  private parametersValue: Record<string, number> = {};
  private routeVersion = 0;
  private lastEventType: SoundEngineEvent["type"] | null = null;
  private lastError: string | null = null;
  private contextStateListener: (() => void) | null = null;

  constructor({ id, label, profile, context, ownsContext = context === undefined }: LegacyWebAudioEngineOptions) {
    this.id = id;
    this.label = label;
    this.profile = profile;
    this.contextValue = context ?? null;
    this.ownsContext = ownsContext;
    if (context) this.initializeGraph(context);
  }

  async start() {
    this.assertUsable();
    if (this.contextValue?.state === "running") {
      this.syncStateFromContext();
      return;
    }
    this.stateValue = "starting";
    this.emit();
    const context = this.ensureContext();
    await this.resumeContext(context);
  }

  async resume() {
    this.assertUsable();
    const context = this.ensureContext();
    await this.resumeContext(context);
  }

  async suspend() {
    if (this.stateValue === "disposed" || this.stateValue === "closed") return;
    const context = this.contextValue;
    if (!context || context.state === "closed") return;
    try {
      if (context.state === "running") await context.suspend();
      this.syncStateFromContext();
    } catch (error) {
      this.setError(error);
    }
  }

  dispatch(events: SoundEngineEvent | readonly SoundEngineEvent[]) {
    this.assertUsable();
    const context = this.ensureContext();
    if (context.state === "suspended") void this.resume();

    const batch = Array.isArray(events) ? [...events] : [events];
    for (const event of batch) validateSoundEngineEvent(event);

    const clock = this.clock();
    const timedEvents = batch
      .map((event, index) => ({
        event,
        index,
        at: Math.max(context.currentTime, resolveEventTimeSeconds(event.time, clock)),
      }))
      .sort((left, right) => left.at - right.at || left.index - right.index);

    const plannedReleaseBySource = new Map<string, number>();
    for (const item of timedEvents) {
      if (item.event.type !== "note-off") continue;
      const previous = plannedReleaseBySource.get(item.event.sourceId);
      if (previous === undefined || item.at < previous) plannedReleaseBySource.set(item.event.sourceId, item.at);
    }

    for (const item of timedEvents) {
      this.lastEventType = item.event.type;
      switch (item.event.type) {
        case "note-on":
          this.startNote(item.event, item.at, plannedReleaseBySource.get(item.event.sourceId) ?? null);
          break;
        case "note-off":
          this.stopNote(item.event, item.at);
          break;
        case "sustain":
        case "sostenuto":
        case "una-corda":
          this.applyPedal(item.event, item.at);
          break;
        case "parameter":
          this.applyParameter(item.event, item.at);
          break;
        case "metronome":
          this.playMetronome(item.event, item.at);
          break;
      }
    }
    this.emit();
  }

  stopAll(time?: SoundEventTime) {
    const context = this.contextValue;
    if (!context || context.state === "closed") {
      this.voices.clear();
      this.emit();
      return;
    }
    const at = Math.max(context.currentTime, resolveEventTimeSeconds(time, this.clock()));
    for (const voice of [...this.voices.values()]) this.releaseVoice(voice, at, 0.04, true);
    this.voices.clear();
    this.emit();
  }

  async handleRouteChange() {
    this.routeVersion += 1;
    this.syncStateFromContext();
    this.emit();
  }

  async dispose() {
    if (this.stateValue === "disposed") return;
    const context = this.contextValue;
    this.stopAll();
    if (context && this.contextStateListener) {
      context.removeEventListener("statechange", this.contextStateListener);
      this.contextStateListener = null;
    }
    try {
      this.compressor?.disconnect();
      this.masterGain?.disconnect();
    } catch {
      // Nodes may already be disconnected after an external context closes.
    }
    this.compressor = null;
    this.masterGain = null;
    if (context && this.ownsContext && context.state !== "closed") {
      try {
        await context.close();
      } catch (error) {
        this.lastError = errorMessage(error);
      }
    }
    this.contextValue = null;
    this.stateValue = "disposed";
    this.emit();
    this.listeners.clear();
  }

  clock(): SoundEngineClock {
    const context = this.contextValue;
    if (!context) {
      return {
        sampleRate: 0,
        currentTimeSeconds: 0,
        currentSampleFrame: 0,
        state: "unavailable",
        baseLatencySeconds: null,
        outputLatencySeconds: null,
      };
    }
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
      ready: Boolean(this.contextValue && !["idle", "starting", "error", "closed", "disposed"].includes(this.stateValue)),
      profile: this.profile,
      activeVoices: this.voices.size,
      pedals: { ...this.pedalsValue },
      parameters: { ...this.parametersValue },
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
    if (this.contextValue) {
      if (!this.masterGain) this.initializeGraph(this.contextValue);
      return this.contextValue;
    }
    if (typeof window === "undefined" || !window.AudioContext) {
      throw new Error("Web Audio is unavailable in this environment.");
    }
    const context = new window.AudioContext({ latencyHint: "interactive" });
    this.contextValue = context;
    this.initializeGraph(context);
    return context;
  }

  private initializeGraph(context: AudioContext) {
    if (this.masterGain) return;
    const masterGain = context.createGain();
    masterGain.gain.value = 1;
    masterGain.connect(context.destination);
    this.masterGain = masterGain;

    if (this.profile === "interactive-piano") {
      const compressor = context.createDynamicsCompressor();
      compressor.threshold.value = -20;
      compressor.knee.value = 18;
      compressor.ratio.value = 6;
      compressor.attack.value = 0.003;
      compressor.release.value = 0.2;
      compressor.connect(masterGain);
      this.compressor = compressor;
    }

    this.contextStateListener = () => {
      this.syncStateFromContext();
      this.emit();
    };
    context.addEventListener("statechange", this.contextStateListener);
    this.syncStateFromContext();
  }

  private async resumeContext(context: AudioContext) {
    try {
      if (context.state === "suspended") await context.resume();
      this.lastError = null;
      this.syncStateFromContext();
    } catch (error) {
      // Autoplay policy can keep a context suspended until a later user gesture.
      this.lastError = errorMessage(error);
      this.stateValue = context.state === "suspended" ? "suspended" : "error";
      this.emit();
    }
  }

  private syncStateFromContext() {
    const context = this.contextValue;
    if (!context) {
      if (this.stateValue !== "disposed") this.stateValue = "idle";
      return;
    }
    if (context.state === "running") this.stateValue = "running";
    else if (context.state === "suspended") this.stateValue = "suspended";
    else this.stateValue = "closed";
  }

  private startNote(event: NoteOnEvent, startTime: number, plannedReleaseTime: number | null) {
    const context = this.ensureContext();
    const previous = this.voices.get(event.sourceId);
    if (previous) {
      this.releaseVoice(previous, startTime, 0.03, true);
      this.voices.delete(event.sourceId);
    }

    const frequency = midiToFrequency(event.note);
    const gain = context.createGain();
    const filter = context.createBiquadFilter();
    const output = this.compressor ?? this.masterGain;
    if (!output) throw new Error("Legacy Web Audio output graph is not initialized.");

    let oscillators: OscillatorNode[];
    let sustainLevel: number;
    if (this.profile === "lesson-tone") {
      const level = event.gain ?? 0.18;
      const duration = plannedReleaseTime === null ? null : Math.max(0.001, plannedReleaseTime - startTime);
      sustainLevel = Math.max(0.025, level * 0.36);
      filter.type = "lowpass";
      filter.frequency.setValueAtTime(3100, startTime);
      gain.gain.setValueAtTime(0.0001, startTime);
      gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, level), startTime + 0.008);
      const decayDuration = duration === null ? 0.22 : Math.min(0.22, Math.max(0.009, duration * 0.5));
      gain.gain.exponentialRampToValueAtTime(sustainLevel, startTime + decayDuration);
      if (plannedReleaseTime !== null) {
        gain.gain.exponentialRampToValueAtTime(0.0001, plannedReleaseTime + 0.16);
      }

      const fundamental = context.createOscillator();
      const overtone = context.createOscillator();
      const overtoneGain = context.createGain();
      fundamental.type = "triangle";
      overtone.type = "sine";
      fundamental.frequency.setValueAtTime(frequency, startTime);
      overtone.frequency.setValueAtTime(frequency * 2, startTime);
      overtoneGain.gain.value = 0.16;
      fundamental.connect(gain);
      overtone.connect(overtoneGain);
      overtoneGain.connect(gain);
      oscillators = [fundamental, overtone];
    } else {
      const level = event.gain ?? 1;
      const unaCordaScale = 1 - this.pedalsValue.unaCorda * 0.16;
      sustainLevel = Math.max(0.0001, 0.16 * level * unaCordaScale);
      filter.type = "lowpass";
      filter.frequency.setValueAtTime(Math.min(5200, 1600 + frequency * 5), startTime);
      filter.Q.value = 0.7;
      gain.gain.setValueAtTime(0.0001, startTime);
      gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, 0.34 * level * unaCordaScale), startTime + 0.008);
      gain.gain.exponentialRampToValueAtTime(sustainLevel, startTime + 0.42);

      const harmonics = [
        { ratio: 1, type: "triangle" as OscillatorType, level: 0.72 },
        { ratio: 2, type: "sine" as OscillatorType, level: 0.19 },
        { ratio: 3, type: "sine" as OscillatorType, level: 0.09 },
      ];
      oscillators = harmonics.map(({ ratio, type, level: partialLevel }) => {
        const oscillator = context.createOscillator();
        const partialGain = context.createGain();
        oscillator.type = type;
        oscillator.frequency.setValueAtTime(frequency * ratio, startTime);
        partialGain.gain.value = partialLevel;
        oscillator.connect(partialGain);
        partialGain.connect(gain);
        return oscillator;
      });
    }

    gain.connect(filter);
    filter.connect(output);
    const voice: LegacyVoice = {
      sourceId: event.sourceId,
      note: event.note,
      gain,
      oscillators,
      sustainLevel,
      released: false,
      capturedBySostenuto: false,
      releaseScheduledAt: this.profile === "lesson-tone" ? plannedReleaseTime : null,
    };
    this.voices.set(event.sourceId, voice);
    for (const oscillator of oscillators) {
      oscillator.start(startTime);
      if (this.profile === "lesson-tone" && plannedReleaseTime !== null) {
        oscillator.stop(plannedReleaseTime + 0.18);
      }
    }
    const firstOscillator = oscillators[0];
    firstOscillator.addEventListener("ended", () => {
      if (this.voices.get(event.sourceId) === voice) {
        this.voices.delete(event.sourceId);
        this.emit();
      }
    }, { once: true });
  }

  private stopNote(event: NoteOffEvent, at: number) {
    const voice = this.voices.get(event.sourceId);
    if (!voice || voice.note !== event.note) return;
    voice.released = true;
    const immediate = at <= this.clock().currentTimeSeconds + 0.005;
    if (immediate && this.shouldHoldReleasedVoice(voice)) {
      this.emit();
      return;
    }
    const releaseSeconds = this.profile === "lesson-tone" ? 0.16 : 0.28;
    this.releaseVoice(voice, at, releaseSeconds, false);
  }

  private releaseVoice(voice: LegacyVoice, at: number, releaseSeconds: number, force: boolean) {
    if (!force && voice.releaseScheduledAt !== null && voice.releaseScheduledAt <= at) return;
    const context = this.contextValue;
    if (!context || context.state === "closed") return;
    const releaseAt = Math.max(context.currentTime, at);
    const parameter = voice.gain.gain;
    if (typeof parameter.cancelAndHoldAtTime === "function") {
      parameter.cancelAndHoldAtTime(releaseAt);
    } else {
      parameter.cancelScheduledValues(releaseAt);
      parameter.setValueAtTime(Math.max(0.0001, voice.sustainLevel), releaseAt);
    }
    parameter.exponentialRampToValueAtTime(0.0001, releaseAt + releaseSeconds);
    const stopAt = releaseAt + releaseSeconds + 0.02;
    for (const oscillator of voice.oscillators) {
      try {
        oscillator.stop(stopAt);
      } catch {
        // A voice can already be stopped when stop-all races a scheduled release.
      }
    }
    voice.releaseScheduledAt = releaseAt;
    voice.released = true;
  }

  private applyPedal(event: PedalEvent, at: number) {
    const previous = this.pedalsValue;
    if (event.type === "sustain") {
      this.pedalsValue = { ...previous, sustain: event.position };
      if (previous.sustain >= 0.5 && event.position < 0.5) this.releaseDeferredVoices(at);
      return;
    }
    if (event.type === "sostenuto") {
      const pressed = previous.sostenuto < 0.5 && event.position >= 0.5;
      this.pedalsValue = { ...previous, sostenuto: event.position };
      if (pressed) {
        for (const voice of this.voices.values()) {
          if (!voice.released) voice.capturedBySostenuto = true;
        }
      }
      if (previous.sostenuto >= 0.5 && event.position < 0.5) {
        for (const voice of this.voices.values()) voice.capturedBySostenuto = false;
        this.releaseDeferredVoices(at);
      }
      return;
    }
    this.pedalsValue = { ...previous, unaCorda: event.position };
  }

  private releaseDeferredVoices(at: number) {
    const releaseSeconds = this.profile === "lesson-tone" ? 0.16 : 0.28;
    for (const voice of this.voices.values()) {
      if (voice.released && !this.shouldHoldReleasedVoice(voice)) {
        this.releaseVoice(voice, at, releaseSeconds, false);
      }
    }
  }

  private shouldHoldReleasedVoice(voice: LegacyVoice) {
    return this.pedalsValue.sustain >= 0.5
      || (this.pedalsValue.sostenuto >= 0.5 && voice.capturedBySostenuto);
  }

  private applyParameter(event: ParameterEvent, at: number) {
    this.parametersValue = { ...this.parametersValue, [event.parameterId]: event.value };
    if (event.parameterId !== "master-gain" || !this.masterGain) return;
    const value = Math.max(0, Math.min(4, event.value));
    this.masterGain.gain.setTargetAtTime(value, at, 0.01);
  }

  private playMetronome(event: MetronomeEvent, at: number) {
    const context = this.ensureContext();
    const output = this.masterGain;
    if (!output) throw new Error("Legacy Web Audio output graph is not initialized.");
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(event.accent ? 1050 : 760, at);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(event.accent ? 0.16 : 0.1, at + 0.002);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.055);
    oscillator.connect(gain);
    gain.connect(output);
    oscillator.start(at);
    oscillator.stop(at + 0.06);
  }

  private assertUsable() {
    if (this.stateValue === "disposed") throw new Error(`Sound engine ${this.id} has been disposed.`);
  }

  private setError(error: unknown) {
    this.lastError = errorMessage(error);
    this.stateValue = "error";
    this.emit();
  }

  private emit() {
    const snapshot = this.snapshot();
    for (const listener of this.listeners) {
      try {
        listener(snapshot);
      } catch {
        // Diagnostics listeners must never break sound generation.
      }
    }
  }
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
