"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Pause, Play, Pulse, Stop } from "@phosphor-icons/react";

import {
  BROWSER_SOUND_ENGINES,
  createBrowserSoundEngine,
  type BrowserSoundEngineId,
} from "@/lib/audio/engine-registry";
import { scheduleMetronome } from "@/lib/audio/scheduler";
import { NOW, type SoundEngine, type SoundEngineSnapshot } from "@/lib/audio/sound-engine";
import { PracticeTransport, type TransportSnapshot } from "@/lib/engine/transport";
import { mariageAmourContent } from "@/lib/music/content/mariage-amour";
import { beatsToSeconds } from "@/lib/music/tempo";

type LogEntry = {
  id: number;
  source: string;
  beat: number;
  performanceTime: number;
  audioTime: number;
  dispatchDelay: number;
};

const EMPTY_SNAPSHOT: TransportSnapshot = { state: "idle", beat: -1, audioTime: 0, performanceTime: 0 };

export function EngineLab() {
  const transportRef = useRef<PracticeTransport | null>(null);
  const engineRef = useRef<SoundEngine | null>(null);
  const unsubscribeEngineRef = useRef<(() => void) | null>(null);
  const rafRef = useRef<number | null>(null);
  const logSerialRef = useRef(0);
  const labAttemptRef = useRef(0);
  const releaseTimersRef = useRef<number[]>([]);
  const frameWindowRef = useRef({ startedAt: 0, lastAt: 0, frames: 0, largestGap: 0 });
  const [selectedEngineId, setSelectedEngineId] = useState<BrowserSoundEngineId>("physical-c4");
  const [snapshot, setSnapshot] = useState(EMPTY_SNAPSHOT);
  const [engineSnapshot, setEngineSnapshot] = useState<SoundEngineSnapshot | null>(null);
  const [startupError, setStartupError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [frameHealth, setFrameHealth] = useState({ fps: 0, largestGap: 0 });
  const [pedals, setPedals] = useState({ sustain: 0, sostenuto: 0, unaCorda: 0 });

  const disposeEngine = useCallback(async () => {
    releaseTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    releaseTimersRef.current = [];
    unsubscribeEngineRef.current?.();
    unsubscribeEngineRef.current = null;
    const engine = engineRef.current;
    engineRef.current = null;
    if (engine) await engine.dispose();
    setEngineSnapshot(null);
  }, []);

  const activateEngine = useCallback(async (id: BrowserSoundEngineId, context: AudioContext) => {
    await disposeEngine();
    const engine = createBrowserSoundEngine(id, { context, ownsContext: false });
    engineRef.current = engine;
    unsubscribeEngineRef.current = engine.subscribe(setEngineSnapshot);
    await engine.start();
    setEngineSnapshot(engine.snapshot());
    return engine;
  }, [disposeEngine]);

  const runAnimation = useCallback((transport: PracticeTransport, engine: SoundEngine) => {
    const tick = () => {
      const now = performance.now();
      const window = frameWindowRef.current;
      if (window.startedAt === 0) {
        window.startedAt = now;
        window.lastAt = now;
      }
      window.frames += 1;
      window.largestGap = Math.max(window.largestGap, now - window.lastAt);
      window.lastAt = now;
      if (now - window.startedAt >= 500) {
        setFrameHealth({
          fps: Math.round((window.frames * 1000) / (now - window.startedAt)),
          largestGap: Math.round(window.largestGap * 10) / 10,
        });
        frameWindowRef.current = { startedAt: now, lastAt: now, frames: 0, largestGap: 0 };
      }
      const next = transport.snapshot();
      setSnapshot(next);
      setEngineSnapshot(engine.snapshot());
      if (next.state === "completed") return;
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const stopLab = useCallback(async () => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    await disposeEngine();
    await transportRef.current?.stop();
    transportRef.current = null;
    setSnapshot(EMPTY_SNAPSHOT);
  }, [disposeEngine]);

  const start = useCallback(async () => {
    const attempt = labAttemptRef.current + 1;
    labAttemptRef.current = attempt;
    setStartupError(null);
    try {
      await stopLab();
      if (labAttemptRef.current !== attempt) return;
      const transport = new PracticeTransport({ bpm: 60, totalBeats: 8, countInBeats: 1 });
      transportRef.current = transport;
      const context = await transport.start();
      if (labAttemptRef.current !== attempt) {
        await transport.stop();
        return;
      }
      const engine = await activateEngine(selectedEngineId, context);
      if (labAttemptRef.current !== attempt) {
        await engine.dispose();
        return;
      }
      setLogs([]);
      setFrameHealth({ fps: 0, largestGap: 0 });
      setPedals({ sustain: 0, sostenuto: 0, unaCorda: 0 });
      frameWindowRef.current = { startedAt: 0, lastAt: 0, frames: 0, largestGap: 0 };
      for (let beat = -1; beat < 8; beat += 1) {
        scheduleMetronome(engine, transport.startTime + beat * beatsToSeconds(1, 60), beat % 3 === 0);
      }
      runAnimation(transport, engine);
    } catch (error) {
      if (labAttemptRef.current !== attempt) return;
      const message = errorMessage(error);
      await stopLab();
      if (labAttemptRef.current !== attempt) return;
      if (message !== "Sound engine was disposed during startup.") {
        setStartupError(message);
      }
    }
  }, [activateEngine, runAnimation, selectedEngineId, stopLab]);

  const selectEngine = useCallback(async (id: BrowserSoundEngineId) => {
    const attempt = labAttemptRef.current + 1;
    labAttemptRef.current = attempt;
    setSelectedEngineId(id);
    setStartupError(null);
    const transport = transportRef.current;
    const context = transport?.context;
    if (!transport || !context || context.state === "closed") return;
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    try {
      const engine = await activateEngine(id, context);
      if (labAttemptRef.current !== attempt) {
        await engine.dispose();
        return;
      }
      runAnimation(transport, engine);
    } catch (error) {
      if (labAttemptRef.current !== attempt) return;
      const message = errorMessage(error);
      await stopLab();
      if (labAttemptRef.current !== attempt) return;
      if (message !== "Sound engine was disposed during startup.") {
        setStartupError(message);
      }
    }
  }, [activateEngine, runAnimation, stopLab]);

  const record = useCallback((source: string, eventTimeStamp = performance.now(), notes: number[] = [60]) => {
    const transport = transportRef.current;
    const engine = engineRef.current;
    if (!transport || !engine) return;
    const at = engine.clock().currentTimeSeconds;
    const serial = logSerialRef.current + 1;
    const sources = notes.map((_note, index) => `lab-${source}-${serial}-${index}`);
    engine.dispatch(notes.map((note, index) => ({
      type: "note-on" as const,
      sourceId: sources[index],
      note,
      velocity: 0.8,
      gain: BROWSER_SOUND_ENGINES.find((candidate) => candidate.id === selectedEngineId)?.labLevel ?? 0.24,
      time: NOW,
    })));
    releaseTimersRef.current.push(window.setTimeout(() => {
      if (engineRef.current !== engine) return;
      engine.dispatch(notes.map((note, index) => ({
        type: "note-off" as const,
        sourceId: sources[index],
        note,
        releaseVelocity: 0.5,
        time: NOW,
      })));
    }, 800));
    logSerialRef.current = serial;
    setLogs((current) => [{
      id: serial,
      source,
      beat: transport.beat(),
      performanceTime: performance.now(),
      audioTime: at,
      dispatchDelay: Math.max(0, performance.now() - eventTimeStamp),
    }, ...current].slice(0, 12));
  }, [selectedEngineId]);

  const setPedal = useCallback((type: "sustain" | "sostenuto" | "una-corda", position: number) => {
    const engine = engineRef.current;
    if (!engine) return;
    engine.dispatch({ type, position, time: NOW });
    setPedals((current) => ({
      ...current,
      [type === "una-corda" ? "unaCorda" : type]: position,
    }));
  }, []);

  const togglePause = useCallback(async () => {
    const transport = transportRef.current;
    if (!transport) return;
    if (transport.snapshot().state === "paused") await transport.resume();
    else await transport.pause();
    setSnapshot(transport.snapshot());
    if (engineRef.current) setEngineSnapshot(engineRef.current.snapshot());
  }, []);

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if (event.repeat || event.code !== "Space") return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("button, a, input, textarea, select")) return;
      event.preventDefault();
      record("keyboard-space", event.timeStamp);
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [record]);

  const stopCurrentLab = useCallback(async () => {
    labAttemptRef.current += 1;
    await stopLab();
  }, [stopLab]);

  useEffect(() => () => {
    labAttemptRef.current += 1;
    void stopLab();
  }, [stopLab]);

  const engineClock = engineSnapshot?.clock;

  return (
    <main className="engine-lab">
      <header>
        <Link href="/"><ArrowLeft size={20} />返回产品</Link>
        <div><Pulse size={24} weight="fill" /><h1>练习引擎诊断台</h1></div>
        <span>仅开发使用</span>
      </header>

      <section className="lab-grid">
        <article className="lab-card lab-clock">
          <h2>声音引擎</h2>
          <label>
            当前实现
            <select
              value={selectedEngineId}
              onChange={(event: React.ChangeEvent<HTMLSelectElement>) => void selectEngine(event.target.value as BrowserSoundEngineId)}
            >
              {BROWSER_SOUND_ENGINES.map((engine) => (
                <option value={engine.id} key={engine.id}>{engine.label}</option>
              ))}
            </select>
          </label>
          <p>{BROWSER_SOUND_ENGINES.find((engine) => engine.id === selectedEngineId)?.description}</p>
          <dl>
            <div><dt>状态</dt><dd>{engineSnapshot?.state ?? "未启动"}</dd></div>
            <div><dt>就绪</dt><dd>{engineSnapshot?.ready ? "是" : "否"}</dd></div>
            <div><dt>活动 voice</dt><dd>{engineSnapshot?.activeVoices ?? 0}</dd></div>
            <div><dt>最后事件</dt><dd>{engineSnapshot?.lastEventType ?? "—"}</dd></div>
            <div><dt>最后错误</dt><dd>{engineSnapshot?.lastError ?? startupError ?? "—"}</dd></div>
            <div><dt>路由版本</dt><dd>{engineSnapshot?.routeVersion ?? 0}</dd></div>
            <div><dt>render block</dt><dd>{engineSnapshot?.parameters.blockSize ?? "—"} frames</dd></div>
            <div><dt>deadline ratio</dt><dd>{typeof engineSnapshot?.parameters.renderDeadlineRatio === "number" ? engineSnapshot.parameters.renderDeadlineRatio.toFixed(3) : "—"}</dd></div>
            <div><dt>WASM memory</dt><dd>{typeof engineSnapshot?.parameters.wasmMemoryBytes === "number" ? Math.round(engineSnapshot.parameters.wasmMemoryBytes / 1024) : "—"} KiB</dd></div>
            <div><dt>underruns</dt><dd>{engineSnapshot?.parameters.underruns ?? "—"}</dd></div>
            <div><dt>late events</dt><dd>{engineSnapshot?.parameters.lateEvents ?? "—"}</dd></div>
          </dl>
          <div className="dialog-actions">
            <button type="button" onClick={() => void start()}><Play size={18} weight="fill" />启动</button>
            <button type="button" onClick={() => void togglePause()}><Pause size={18} weight="fill" />暂停/继续</button>
            <button type="button" onClick={() => void stopCurrentLab()}><Stop size={18} weight="fill" />停止</button>
          </div>
          <button type="button" className="lab-link" onClick={() => void engineRef.current?.handleRouteChange()}>模拟输出路由变化</button>
        </article>

        <article className="lab-card lab-clock">
          <h2>统一时钟</h2>
          <dl>
            <div><dt>Transport</dt><dd>{snapshot.state}</dd></div>
            <div><dt>当前拍</dt><dd>{snapshot.beat.toFixed(3)}</dd></div>
            <div><dt>AudioContext</dt><dd>{(engineClock?.currentTimeSeconds ?? 0).toFixed(3)} s</dd></div>
            <div><dt>sample frame</dt><dd>{engineClock?.currentSampleFrame ?? 0}</dd></div>
            <div><dt>采样率</dt><dd>{engineClock?.sampleRate ?? 0} Hz</dd></div>
            <div><dt>base latency</dt><dd>{engineClock?.baseLatencySeconds?.toFixed(4) ?? "—"} s</dd></div>
            <div><dt>output latency</dt><dd>{engineClock?.outputLatencySeconds?.toFixed(4) ?? "—"} s</dd></div>
            <div><dt>画面帧率</dt><dd>{frameHealth.fps || "—"} FPS</dd></div>
            <div><dt>最大帧间隔</dt><dd>{frameHealth.largestGap || "—"} ms</dd></div>
          </dl>
        </article>

        <article className="lab-card lab-input">
          <h2>输入事件</h2>
          <button type="button" className="lab-tap" onPointerDown={(event: React.PointerEvent<HTMLButtonElement>) => record("pointer-c4", event.timeStamp)}>C4 · 点击或空格</button>
          <div className="dialog-actions">
            <button type="button" disabled={selectedEngineId === "physical-c4"} onClick={(event: React.MouseEvent<HTMLButtonElement>) => record("c-major", event.timeStamp, [60, 64, 67])}>C 大三和弦</button>
            <button type="button" disabled={selectedEngineId === "physical-c4"} onClick={(event: React.MouseEvent<HTMLButtonElement>) => record("wide-chord", event.timeStamp, [48, 60, 67, 72])}>宽音域和弦</button>
          </div>
          <ol>
            {logs.length === 0 ? <li className="empty">启动时钟后记录事件</li> : logs.map((entry) => (
              <li key={entry.id}><b>{entry.source}</b><span>beat {entry.beat.toFixed(3)}</span><small>分发 {entry.dispatchDelay.toFixed(1)} ms</small></li>
            ))}
          </ol>
        </article>

        <article className="lab-card lab-input">
          <h2>踏板事件</h2>
          <label>
            Sustain {Math.round(pedals.sustain * 100)}%
            <input type="range" min="0" max="1" step="0.01" value={pedals.sustain} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setPedal("sustain", Number(event.target.value))} />
          </label>
          <label>
            Sostenuto {Math.round(pedals.sostenuto * 100)}%
            <input type="range" min="0" max="1" step="0.01" value={pedals.sostenuto} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setPedal("sostenuto", Number(event.target.value))} />
          </label>
          <label>
            Una corda {Math.round(pedals.unaCorda * 100)}%
            <input type="range" min="0" max="1" step="0.01" value={pedals.unaCorda} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setPedal("una-corda", Number(event.target.value))} />
          </label>
          <div className="dialog-actions">
            <button type="button" onClick={() => setPedal("sustain", pedals.sustain >= 0.5 ? 0 : 1)}>切换延音</button>
            <button type="button" onClick={() => {
              setPedal("sustain", 0);
              setPedal("sostenuto", 0);
              setPedal("una-corda", 0);
            }}>释放全部</button>
          </div>
        </article>

        <article className="lab-card lab-content">
          <h2>内容包</h2>
          <dl>
            <div><dt>曲目</dt><dd>{mariageAmourContent.title}</dd></div>
            <div><dt>校准事件</dt><dd>{mariageAmourContent.events.length}</dd></div>
            <div><dt>可运行练习</dt><dd>{mariageAmourContent.exercises.length}</dd></div>
            <div><dt>拍号</dt><dd>{mariageAmourContent.beatsPerMeasure}/4</dd></div>
            <div><dt>参考速度</dt><dd>{mariageAmourContent.referenceBpm} BPM</dd></div>
          </dl>
          <Link className="lab-link" href="/practice/B1-02">打开节奏关卡</Link>
        </article>
      </section>
    </main>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
