"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowCounterClockwise,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  HandTap,
  Pause,
  Play,
  SpeakerHigh,
} from "@phosphor-icons/react";

import { scheduleMetronome, scheduleMidiTone } from "@/lib/audio/scheduler";
import {
  evaluateRhythmAttempt,
  findNearestRhythmTarget,
  type RhythmResult,
  type RhythmTap,
  type RhythmTarget,
} from "@/lib/engine/rhythm-evaluator";
import { PracticeTransport } from "@/lib/engine/transport";
import { getEventsForExercise } from "@/lib/music/content/mariage-amour";
import { beatsToSeconds } from "@/lib/music/tempo";
import { RhythmLane } from "./RhythmLane";

type StageOnePracticeProps = {
  lessonId: "B1-01" | "B1-02";
};

const PHRASE_BEATS = 6;

function eventBeat(measure: number, beat: number) {
  return (measure - 6) * 3 + beat;
}

function useTransportCleanup(transportRef: React.MutableRefObject<PracticeTransport | null>) {
  useEffect(() => () => {
    void transportRef.current?.stop();
    transportRef.current = null;
  }, [transportRef]);
}

function ListenLesson() {
  const events = useMemo(() => getEventsForExercise("B1-01"), []);
  const transportRef = useRef<PracticeTransport | null>(null);
  const rafRef = useRef<number | null>(null);
  const [status, setStatus] = useState<"ready" | "listening" | "question" | "correct">("ready");
  const [currentBeat, setCurrentBeat] = useState(-0.2);
  const [message, setMessage] = useState("先闭上眼睛听一次，不需要看谱。");
  useTransportCleanup(transportRef);

  const stopAnimation = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  }, []);

  const playDemo = useCallback(async () => {
    stopAnimation();
    await transportRef.current?.stop();
    const transport = new PracticeTransport({ bpm: 75, totalBeats: PHRASE_BEATS });
    transportRef.current = transport;
    const context = await transport.start();
    setCurrentBeat(0);
    setStatus("listening");
    setMessage("听一听：长音之后，短音怎样排列？");

    for (const item of events) {
      const beat = eventBeat(item.measure, item.beat);
      scheduleMidiTone(context, item.midi, transport.startTime + beatsToSeconds(beat, 75), beatsToSeconds(item.durationBeats, 75));
    }

    const frame = () => {
      const snapshot = transport.snapshot();
      setCurrentBeat(snapshot.beat);
      if (snapshot.state === "completed") {
        stopAnimation();
        setStatus("question");
        setMessage("你听到的是哪一种长短规律？");
        void transport.stop();
        return;
      }
      rafRef.current = requestAnimationFrame(frame);
    };
    rafRef.current = requestAnimationFrame(frame);
  }, [events, stopAnimation]);

  function choose(correct: boolean) {
    if (correct) {
      setStatus("correct");
      setMessage("听对了：一个长音接四个短音，然后重复一次。");
    } else {
      setMessage("再听一次，注意每小节开头较长的第一个音。");
      setStatus("ready");
    }
  }

  return (
    <section className="lesson-card listen-card" aria-labelledby="lesson-title">
      <div className="lesson-kicker">听辨 · 第 6–7 小节</div>
      <h1 id="lesson-title">先听见节奏</h1>
      <p className="lesson-lead">{message}</p>

      <div className={`listening-orb${status === "listening" ? " active" : ""}`} aria-hidden="true">
        <span>♪</span>
        <i style={{ transform: `scaleX(${Math.max(0.04, Math.min(1, currentBeat / PHRASE_BEATS))})` }} />
      </div>

      {status === "ready" || status === "listening" ? (
        <button type="button" className="moon-primary" onClick={() => void playDemo()} disabled={status === "listening"}>
          <SpeakerHigh size={22} weight="fill" />
          {status === "listening" ? "正在播放…" : "播放慢速示范"}
        </button>
      ) : null}

      {status === "question" ? (
        <div className="rhythm-options" role="group" aria-label="选择节奏轮廓">
          <button type="button" onClick={() => choose(true)}><b>长</b><span>短 · 短 · 短 · 短</span><small>重复一次</small></button>
          <button type="button" onClick={() => choose(false)}><b>均匀</b><span>六个一样长的音</span><small>重复一次</small></button>
        </div>
      ) : null}

      {status === "correct" ? (
        <div className="lesson-success">
          <CheckCircle size={30} weight="fill" />
          <div><b>节奏轮廓已记住</b><span>下一关，把听到的节奏亲手弹出来。</span></div>
          <Link href="/practice/B1-02">继续 <ArrowRight size={18} weight="bold" /></Link>
        </div>
      ) : null}
    </section>
  );
}

function buildRhythmTargets(): RhythmTarget[] {
  const base = getEventsForExercise("B1-02").map((item) => ({
    id: item.id,
    beat: eventBeat(item.measure, item.beat),
    durationBeats: item.durationBeats,
  }));
  return [0, 1].flatMap((loop) => base.map((target) => ({
    ...target,
    id: `${target.id}-loop-${loop + 1}`,
    beat: target.beat + loop * PHRASE_BEATS,
  })));
}

function RhythmLesson() {
  const targets = useMemo(() => buildRhythmTargets(), []);
  const transportRef = useRef<PracticeTransport | null>(null);
  const rafRef = useRef<number | null>(null);
  const tapsRef = useRef<RhythmTap[]>([]);
  const matchedRef = useRef<Set<string>>(new Set());
  const finishedRef = useRef(false);
  const [status, setStatus] = useState<"ready" | "running" | "paused" | "completed">("ready");
  const [currentBeat, setCurrentBeat] = useState(-3);
  const [matchedIds, setMatchedIds] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState("色块到达青色线时，点击下方节奏键。电脑也可以按空格。 ");
  const [result, setResult] = useState<RhythmResult | null>(null);
  useTransportCleanup(transportRef);

  const finish = useCallback(async () => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    const nextResult = evaluateRhythmAttempt(targets, tapsRef.current);
    setResult(nextResult);
    setStatus("completed");
    setFeedback(nextResult.accuracy >= 0.8 ? "节拍站稳了，你已经抓住这段旋律的骨架。" : "已经找到节奏了，再把落点收得更准一些。 ");
    await transportRef.current?.stop();
  }, [targets]);

  const runAnimation = useCallback((transport: PracticeTransport) => {
    const tick = () => {
      const snapshot = transport.snapshot();
      setCurrentBeat(snapshot.beat);
      if (snapshot.state === "completed") {
        void finish();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [finish]);

  const begin = useCallback(async () => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    await transportRef.current?.stop();
    const transport = new PracticeTransport({ bpm: 60, totalBeats: PHRASE_BEATS * 2, countInBeats: 3 });
    transportRef.current = transport;
    const context = await transport.start();
    tapsRef.current = [];
    matchedRef.current = new Set();
    finishedRef.current = false;
    setMatchedIds(new Set());
    setResult(null);
    setCurrentBeat(-3);
    setStatus("running");
    setFeedback("先听三拍倒数，然后跟着色块弹两轮。 ");

    const secondsPerBeat = beatsToSeconds(1, 60);
    for (let beat = -3; beat < PHRASE_BEATS * 2; beat += 1) {
      scheduleMetronome(context, transport.startTime + beat * secondsPerBeat, beat % 3 === 0);
    }
    runAnimation(transport);
  }, [runAnimation]);

  const tap = useCallback(() => {
    const transport = transportRef.current;
    if (!transport || status !== "running") return;
    const beat = transport.beat();
    if (beat < 0 || beat >= PHRASE_BEATS * 2) return;
    const tapEvent = { id: `tap-${tapsRef.current.length + 1}`, beat };
    tapsRef.current.push(tapEvent);
    const nearest = findNearestRhythmTarget(targets, beat, matchedRef.current);
    if (!nearest) {
      setFeedback("再等等，让色块更靠近青色线。 ");
      return;
    }
    matchedRef.current.add(nearest.target.id);
    setMatchedIds(new Set(matchedRef.current));
    const absolute = Math.abs(nearest.delta);
    setFeedback(absolute <= 0.14 ? "正好！" : nearest.delta < 0 ? "稍微早了一点" : "稍微晚了一点");
    if (transport.context) scheduleMidiTone(transport.context, 60, transport.context.currentTime, 0.09, 0.09);
  }, [status, targets]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      const isRhythmKey = event.key.length === 1 || event.code === "Space" || event.code === "Enter";
      if (!isRhythmKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("button, a, input, textarea, select")) return;
      event.preventDefault();
      tap();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [tap]);

  async function togglePause() {
    const transport = transportRef.current;
    if (!transport) return;
    if (status === "paused") {
      await transport.resume();
      setStatus("running");
      runAnimation(transport);
      return;
    }
    if (status === "running") {
      await transport.pause();
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      setStatus("paused");
      setFeedback("练习已暂停，准备好后从这里继续。 ");
    }
  }

  const pass = Boolean(result && result.accuracy >= 0.8);
  const accuracyPercent = result ? Math.round(result.accuracy * 100) : 0;
  const progress = Math.max(0, Math.min(1, currentBeat / (PHRASE_BEATS * 2)));
  const countdown = currentBeat < 0 ? Math.max(1, Math.ceil(-currentBeat)) : null;

  return (
    <section className="lesson-card rhythm-card" aria-labelledby="lesson-title">
      <div className="lesson-kicker">纯节奏 · 60 BPM</div>
      <h1 id="lesson-title">跟上月光节拍</h1>
      <p className="lesson-lead" aria-live="polite">{feedback}</p>

      <div className="lesson-progress"><i style={{ transform: `scaleX(${progress})` }} /></div>
      <div className="rhythm-stage">
        <RhythmLane targets={targets} currentBeat={currentBeat} matchedIds={matchedIds} />
        {countdown && status === "running" ? <div className="countdown" aria-live="assertive">{countdown}</div> : null}
      </div>

      {status !== "completed" ? (
        <div className="rhythm-controls">
          <button
            type="button"
            className={`tap-pad${status === "running" ? " active" : ""}`}
            onPointerDown={(event) => { event.preventDefault(); tap(); }}
            disabled={status !== "running"}
          >
            <HandTap size={32} weight="fill" />
            <span>{status === "running" ? "节奏键" : "准备后开始"}</span>
            <small>触控或按空格</small>
          </button>
          <div className="practice-actions">
            {status === "ready" ? (
              <button type="button" className="moon-primary" onClick={() => void begin()}><Play size={19} weight="fill" />开始练习</button>
            ) : (
              <>
                <button type="button" className="moon-secondary" onClick={() => void togglePause()}>
                  {status === "paused" ? <Play size={18} weight="fill" /> : <Pause size={18} weight="fill" />}
                  {status === "paused" ? "继续" : "暂停"}
                </button>
                <button type="button" className="moon-secondary" onClick={() => void begin()}><ArrowCounterClockwise size={18} />重来</button>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className={`rhythm-result ${pass ? "passed" : "retry"}`}>
          <div className="result-score"><strong>{accuracyPercent}%</strong><span>节奏达标率</span></div>
          <div className="result-copy">
            <b>{pass ? "本关完成" : "再练一次就会更稳"}</b>
            <span>命中 {result?.matches.length ?? 0} / {targets.length}，多按 {result?.extras.length ?? 0} 次。</span>
          </div>
          <div className="result-actions">
            <button type="button" className="moon-secondary" onClick={() => void begin()}><ArrowCounterClockwise size={18} />再练一次</button>
            {pass ? <Link className="moon-primary" href="/">完成阶段 1 <ArrowRight size={18} /></Link> : null}
          </div>
        </div>
      )}
    </section>
  );
}

export function StageOnePractice({ lessonId }: StageOnePracticeProps) {
  const step = lessonId === "B1-01" ? 1 : 2;
  return (
    <main className="practice-experience">
      <div className="practice-stars" aria-hidden="true" />
      <header className="practice-topbar">
        <Link href="/" className="practice-exit" aria-label="退出练习"><ArrowLeft size={23} /></Link>
        <div className="practice-course-progress">
          <span>第 1 章 · 听见主题</span>
          <div><i style={{ transform: `scaleX(${step / 7})` }} /></div>
          <small>{step} / 7</small>
        </div>
        <div className="practice-brand">月光琴房</div>
      </header>
      {lessonId === "B1-01" ? <ListenLesson /> : <RhythmLesson />}
      <p className="practice-footnote">第 6–7 小节 · 先听见，再弹出来</p>
    </main>
  );
}
