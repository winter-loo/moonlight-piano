import { beatsToSeconds, secondsToBeats } from "../music/tempo.ts";

export type TransportState = "idle" | "count-in" | "playing" | "paused" | "completed" | "stopped";

export type TransportSnapshot = {
  state: TransportState;
  beat: number;
  audioTime: number;
  performanceTime: number;
};

type TransportConfig = {
  bpm: number;
  totalBeats: number;
  countInBeats?: number;
};

export class PracticeTransport {
  readonly bpm: number;
  readonly totalBeats: number;
  readonly countInBeats: number;
  private contextValue: AudioContext | null = null;
  private startAudioTime = 0;
  private stateValue: TransportState = "idle";

  constructor({ bpm, totalBeats, countInBeats = 0 }: TransportConfig) {
    if (bpm <= 0 || totalBeats <= 0 || countInBeats < 0) throw new Error("Invalid transport configuration.");
    this.bpm = bpm;
    this.totalBeats = totalBeats;
    this.countInBeats = countInBeats;
  }

  get context() {
    return this.contextValue;
  }

  get startTime() {
    return this.startAudioTime;
  }

  async start() {
    await this.stop();
    const context = new AudioContext({ latencyHint: "interactive" });
    await context.resume();
    this.contextValue = context;
    this.startAudioTime = context.currentTime + beatsToSeconds(this.countInBeats, this.bpm);
    this.stateValue = this.countInBeats > 0 ? "count-in" : "playing";
    return context;
  }

  beat() {
    if (!this.contextValue) return -this.countInBeats;
    return secondsToBeats(this.contextValue.currentTime - this.startAudioTime, this.bpm);
  }

  snapshot(): TransportSnapshot {
    const beat = this.beat();
    if (this.stateValue !== "paused" && this.stateValue !== "stopped") {
      if (beat >= this.totalBeats) this.stateValue = "completed";
      else if (beat >= 0) this.stateValue = "playing";
      else this.stateValue = "count-in";
    }
    return {
      state: this.stateValue,
      beat,
      audioTime: this.contextValue?.currentTime ?? 0,
      performanceTime: performance.now(),
    };
  }

  async pause() {
    if (!this.contextValue || this.stateValue === "paused" || this.stateValue === "completed") return;
    await this.contextValue.suspend();
    this.stateValue = "paused";
  }

  async resume() {
    if (!this.contextValue || this.stateValue !== "paused") return;
    await this.contextValue.resume();
    this.stateValue = this.beat() < 0 ? "count-in" : "playing";
  }

  async stop() {
    const context = this.contextValue;
    this.contextValue = null;
    this.stateValue = "stopped";
    if (context && context.state !== "closed") await context.close();
  }
}
