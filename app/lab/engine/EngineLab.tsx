"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Pulse } from "@phosphor-icons/react";

import { scheduleMetronome, scheduleMidiTone } from "@/lib/audio/scheduler";
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
  const rafRef = useRef<number | null>(null);
  const frameWindowRef = useRef({ startedAt: 0, lastAt: 0, frames: 0, largestGap: 0 });
  const [snapshot, setSnapshot] = useState(EMPTY_SNAPSHOT);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [frameHealth, setFrameHealth] = useState({ fps: 0, largestGap: 0 });

  const runAnimation = useCallback((transport: PracticeTransport) => {
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
      if (next.state === "completed") return;
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const start = useCallback(async () => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    await transportRef.current?.stop();
    const transport = new PracticeTransport({ bpm: 60, totalBeats: 8, countInBeats: 1 });
    transportRef.current = transport;
    const context = await transport.start();
    setLogs([]);
    setFrameHealth({ fps: 0, largestGap: 0 });
    frameWindowRef.current = { startedAt: 0, lastAt: 0, frames: 0, largestGap: 0 };
    for (let beat = -1; beat < 8; beat += 1) {
      scheduleMetronome(context, transport.startTime + beat * beatsToSeconds(1, 60), beat % 3 === 0);
    }
    runAnimation(transport);
  }, [runAnimation]);

  const record = useCallback((source: string, eventTimeStamp = performance.now()) => {
    const transport = transportRef.current;
    if (!transport?.context) return;
    scheduleMidiTone(transport.context, 60, transport.context.currentTime, 0.08, 0.08);
    setLogs((current) => [{
      id: current.length + 1,
      source,
      beat: transport.beat(),
      performanceTime: performance.now(),
      audioTime: transport.context?.currentTime ?? 0,
      dispatchDelay: Math.max(0, performance.now() - eventTimeStamp),
    }, ...current].slice(0, 12));
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

  useEffect(() => () => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    void transportRef.current?.stop();
  }, []);

  return (
    <main className="engine-lab">
      <header>
        <Link href="/"><ArrowLeft size={20} />返回产品</Link>
        <div><Pulse size={24} weight="fill" /><h1>练习引擎诊断台</h1></div>
        <span>仅开发使用</span>
      </header>

      <section className="lab-grid">
        <article className="lab-card lab-clock">
          <h2>统一时钟</h2>
          <dl>
            <div><dt>状态</dt><dd>{snapshot.state}</dd></div>
            <div><dt>当前拍</dt><dd>{snapshot.beat.toFixed(3)}</dd></div>
            <div><dt>AudioContext</dt><dd>{snapshot.audioTime.toFixed(3)} s</dd></div>
            <div><dt>performance</dt><dd>{snapshot.performanceTime.toFixed(1)} ms</dd></div>
            <div><dt>画面帧率</dt><dd>{frameHealth.fps || "—"} FPS</dd></div>
            <div><dt>最大帧间隔</dt><dd>{frameHealth.largestGap || "—"} ms</dd></div>
          </dl>
          <button type="button" className="moon-primary" onClick={() => void start()}>启动 60 BPM 测试</button>
        </article>

        <article className="lab-card lab-input">
          <h2>输入事件</h2>
          <button type="button" className="lab-tap" onPointerDown={(event) => record("pointer", event.timeStamp)}>点击或按空格</button>
          <ol>
            {logs.length === 0 ? <li className="empty">启动时钟后记录事件</li> : logs.map((entry) => (
              <li key={entry.id}><b>{entry.source}</b><span>beat {entry.beat.toFixed(3)}</span><small>分发 {entry.dispatchDelay.toFixed(1)} ms</small></li>
            ))}
          </ol>
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
