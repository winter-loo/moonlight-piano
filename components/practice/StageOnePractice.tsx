"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowCounterClockwise,
  ArrowLeft,
  ArrowRight,
  CaretLeft,
  CaretRight,
  CheckCircle,
  Pause,
  Play,
  SpeakerHigh,
  X,
} from "@phosphor-icons/react";

import { scheduleMetronome, scheduleMidiTone } from "@/lib/audio/scheduler";
import {
  evaluateRhythmAttempt,
  findNearestRhythmTarget,
  type RhythmResult,
  type RhythmTap,
} from "@/lib/engine/rhythm-evaluator";
import { PracticeTransport } from "@/lib/engine/transport";
import { getEventsForExercise } from "@/lib/music/content/mariage-amour";
import { beatsToSeconds } from "@/lib/music/tempo";
import { RhythmLane, type StaffRhythmTarget } from "./RhythmLane";
import { SectionTwentyOneScore } from "./SectionTwentyOneScore";
import { VirtualPiano } from "./VirtualPiano";

type StageOnePracticeProps = {
  lessonId: "B1-01" | "B1-02";
};

const PHRASE_BEATS = 6;
const MAIN_LOOPS = 3;
const SHOW_STATIC_SCORE_REVIEW = true;

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
  const events = useMemo(() => getEventsForExercise("B1-01")
    .filter((item) => item.hand === "right" && item.measure === 6)
    .sort((a, b) => a.beat - b.beat), []);
  const contextRef = useRef<AudioContext | null>(null);
  const timersRef = useRef<number[]>([]);
  const [status, setStatus] = useState<"ready" | "demo" | "turn" | "correct">("ready");
  const [step, setStep] = useState(0);
  const [mistakes, setMistakes] = useState(0);
  const [activeMidi, setActiveMidi] = useState<number | null>(null);
  const [wrongMidi, setWrongMidi] = useState<number | null>(null);
  const [message, setMessage] = useState("先看月月弹一遍，再用下面的钢琴原样弹回来。");

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current = [];
  }, []);

  const ensureContext = useCallback(() => {
    if (!contextRef.current) contextRef.current = new AudioContext({ latencyHint: "interactive" });
    if (contextRef.current.state === "suspended") void contextRef.current.resume();
    return contextRef.current;
  }, []);

  useEffect(() => () => {
    clearTimers();
    void contextRef.current?.close();
    contextRef.current = null;
  }, [clearTimers]);

  const playDemo = useCallback(async () => {
    clearTimers();
    const context = ensureContext();
    const secondsPerBeat = beatsToSeconds(1, 75);
    const audioStart = context.currentTime + 0.12;
    setStatus("demo");
    setStep(0);
    setMistakes(0);
    setWrongMidi(null);
    setMessage("看好发亮的琴键，也听一听每个音之间的距离。");

    for (const item of events) {
      const delay = item.beat * secondsPerBeat;
      const duration = item.durationBeats * secondsPerBeat;
      scheduleMidiTone(context, item.midi, audioStart + delay, duration, 0.16);
      timersRef.current.push(window.setTimeout(() => setActiveMidi(item.midi), (delay + 0.12) * 1000));
      timersRef.current.push(window.setTimeout(() => setActiveMidi(null), (delay + 0.12 + Math.min(duration * 0.78, 0.48)) * 1000));
    }
    const endDelay = (3 * secondsPerBeat + 0.35) * 1000;
    timersRef.current.push(window.setTimeout(() => {
      setActiveMidi(null);
      setStatus("turn");
      setMessage("轮到你了！从刚才的第一个音开始。");
    }, endDelay));
  }, [clearTimers, ensureContext, events]);

  const playUserNote = useCallback(async (midi: number) => {
    if (status !== "turn") return;
    const context = ensureContext();
    scheduleMidiTone(context, midi, context.currentTime, 0.42, 0.14);
    setActiveMidi(midi);
    timersRef.current.push(window.setTimeout(() => setActiveMidi(null), 190));

    const expected = events[step]?.midi;
    if (midi !== expected) {
      setWrongMidi(midi);
      setMistakes((current) => current + 1);
      setMessage("不是这个音，再听听脑海里的第一个落点。");
      timersRef.current.push(window.setTimeout(() => setWrongMidi(null), 420));
      return;
    }

    const nextStep = step + 1;
    setWrongMidi(null);
    setMistakes(0);
    setStep(nextStep);
    if (nextStep === events.length) {
      setStatus("correct");
      setMessage("你把整句旋律从耳朵搬到了手上！");
    } else {
      setMessage(nextStep === 1 ? "第一个音对了，继续。" : "对，就是这样。继续弹下一个音。");
    }
  }, [ensureContext, events, status, step]);

  const coachTitle = status === "demo" ? "看我弹一遍" : status === "correct" ? "全部弹对了！" : status === "turn" ? "轮到你了！" : "先听，再弹";
  const hintMidi = status === "turn" && mistakes >= 2 ? events[step]?.midi ?? null : null;

  return (
    <section className="lesson-card listen-card echo-listen-card" aria-labelledby="lesson-title">
      <div className="lesson-kicker">听辨 · 虚拟钢琴跟弹</div>
      <h1 id="lesson-title">{coachTitle}</h1>
      <p className="lesson-lead" aria-live="polite">{message}</p>

      <div className="echo-coach" aria-hidden="true">
        <img src="/assets/moon-panda-coach.png" alt="" />
        <div className="echo-sequence-progress">
          {events.map((event, index) => <i key={event.id} className={index < step ? "done" : index === step && status === "turn" ? "current" : ""} />)}
        </div>
      </div>

      <VirtualPiano
        activeMidi={activeMidi}
        wrongMidi={wrongMidi}
        hintMidi={hintMidi}
        disabled={status !== "turn"}
        onNote={(midi) => void playUserNote(midi)}
      />

      <div className="echo-actions">
        {status === "ready" ? <button type="button" className="moon-primary" onClick={() => void playDemo()}><SpeakerHigh size={22} weight="fill" />听老师弹</button> : null}
        {status === "demo" ? <button type="button" className="moon-secondary" disabled><SpeakerHigh size={20} weight="fill" />正在示范…</button> : null}
        {status === "turn" ? <button type="button" className="moon-secondary" onClick={() => void playDemo()}><ArrowCounterClockwise size={19} />再听一次</button> : null}
      </div>

      {status === "correct" ? (
        <div className="lesson-success">
          <CheckCircle size={30} weight="fill" />
          <div><b>听辨跟弹完成</b><span>下一关保留这句旋律的节奏，暂时隐藏音高。</span></div>
          <Link href="/practice/B1-02">继续 <ArrowRight size={18} weight="bold" /></Link>
        </div>
      ) : null}
    </section>
  );
}

function buildRhythmTargets(loops = MAIN_LOOPS): StaffRhythmTarget[] {
  const base = getEventsForExercise("B1-02").map((item) => ({
    id: item.id,
    beat: eventBeat(item.measure, item.beat),
    durationBeats: item.durationBeats,
    midi: item.midi,
    label: item.spelling.replace(/\d/g, ""),
  }));
  return Array.from({ length: loops }, (_, loop) => loop).flatMap((loop) => base.map((target) => ({
    ...target,
    id: `${target.id}-loop-${loop + 1}`,
    beat: target.beat + loop * PHRASE_BEATS,
  })));
}

function StaticScoreReview() {
  return (
    <main className="section21-score-screen" aria-labelledby="score-review-title">
      <div className="section21-score-progress" aria-hidden="true"><i /></div>
      <Link href="/" className="section21-score-exit" aria-label="返回课程首页"><X size={42} weight="regular" /></Link>

      <header className="section21-score-header">
        <p>产品文档 21.3 · 实机谱面记录</p>
        <h1 id="score-review-title">全部音符</h1>
        <div className="section21-score-stats" aria-label="谱面统计">
          <span><strong>34</strong> 小节</span>
          <span><strong>75</strong> 音符</span>
          <span><strong>10</strong> 休止符</span>
          <span><strong>3/4</strong> 拍</span>
        </div>
      </header>

      <SectionTwentyOneScore />
    </main>
  );
}

function RhythmLesson() {
  const targets = useMemo(() => buildRhythmTargets(), []);
  const transportRef = useRef<PracticeTransport | null>(null);
  const rafRef = useRef<number | null>(null);
  const tapsRef = useRef<RhythmTap[]>([]);
  const matchedRef = useRef<Set<string>>(new Set());
  const finishedRef = useRef(false);
  const activeTimerRef = useRef<number | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const recoveryTimerRef = useRef<number | null>(null);
  const autoStartedRef = useRef(false);
  const resumeAfterExitRef = useRef(false);
  const phaseRef = useRef<"main" | "recovery">("main");
  const activeTargetsRef = useRef<StaffRhythmTarget[]>(targets);
  const attemptTotalRef = useRef(PHRASE_BEATS * MAIN_LOOPS);
  const mainResultRef = useRef<RhythmResult | null>(null);
  const [status, setStatus] = useState<"booting" | "running" | "paused" | "recovery-prompt" | "completed">("booting");
  const [phase, setPhase] = useState<"main" | "recovery">("main");
  const [currentBeat, setCurrentBeat] = useState(-1.5);
  const [activeTargets, setActiveTargets] = useState<StaffRhythmTarget[]>(targets);
  const [retryTargets, setRetryTargets] = useState<StaffRhythmTarget[]>([]);
  const [matchedIds, setMatchedIds] = useState<Set<string>>(new Set());
  const [activeMidi, setActiveMidi] = useState<number | null>(null);
  const [feedback, setFeedback] = useState("让音符抵达判定线时，弹下对应琴键。");
  const [timingToast, setTimingToast] = useState("");
  const [hitSerial, setHitSerial] = useState(0);
  const [result, setResult] = useState<RhythmResult | null>(null);
  const [exitOpen, setExitOpen] = useState(false);
  const [trayOpen, setTrayOpen] = useState(false);
  useTransportCleanup(transportRef);

  useEffect(() => () => {
    if (activeTimerRef.current !== null) window.clearTimeout(activeTimerRef.current);
    if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    if (recoveryTimerRef.current !== null) window.clearTimeout(recoveryTimerRef.current);
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
  }, []);

  const finish = useCallback(async () => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    const attemptTargets = activeTargetsRef.current;
    const nextResult = evaluateRhythmAttempt(attemptTargets, tapsRef.current);
    setActiveMidi(null);
    await transportRef.current?.stop();

    if (phaseRef.current === "main" && nextResult.misses.length > 0) {
      const missed = new Set(nextResult.misses);
      const compactTargets = attemptTargets
        .filter((target) => missed.has(target.id))
        .map((target, index) => ({
          ...target,
          id: `retry-${target.id}`,
          beat: index * 1.25,
          durationBeats: Math.min(1, target.durationBeats),
        }));
      mainResultRef.current = nextResult;
      setRetryTargets(compactTargets);
      setStatus("recovery-prompt");
      setFeedback(`刚才错过了 ${compactTargets.length} 个落点，马上集中练一遍。`);
      return;
    }

    if (phaseRef.current === "recovery" && mainResultRef.current) {
      const original = mainResultRef.current;
      const recovered = nextResult.matches.length;
      const remainingMisses = Math.max(0, original.misses.length - recovered);
      setResult({
        matches: [...original.matches, ...nextResult.matches],
        misses: original.misses.slice(0, remainingMisses),
        extras: [...original.extras, ...nextResult.extras],
        accuracy: (targets.length - remainingMisses) / targets.length,
        meanAbsoluteDeltaBeats: nextResult.meanAbsoluteDeltaBeats,
      });
    } else {
      setResult(nextResult);
    }
    setStatus("completed");
    setFeedback("练习完成，今天的节拍已经稳稳落在手上。");
  }, [targets.length]);

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

  const begin = useCallback(async (nextTargets: StaffRhythmTarget[] = targets, phase: "main" | "recovery" = "main") => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    await transportRef.current?.stop();
    const finalTarget = nextTargets.at(-1);
    const totalBeats = Math.max(2, (finalTarget?.beat ?? 0) + (finalTarget?.durationBeats ?? 1) + 0.5);
    const transport = new PracticeTransport({ bpm: 60, totalBeats, countInBeats: 1.5 });
    transportRef.current = transport;
    const context = await transport.start();
    activeTargetsRef.current = nextTargets;
    attemptTotalRef.current = totalBeats;
    phaseRef.current = phase;
    setPhase(phase);
    tapsRef.current = [];
    matchedRef.current = new Set();
    finishedRef.current = false;
    setActiveTargets(nextTargets);
    setMatchedIds(new Set());
    if (phase === "main") {
      mainResultRef.current = null;
      setResult(null);
      setRetryTargets([]);
    }
    setCurrentBeat(-1.5);
    setStatus("running");
    setActiveMidi(null);
    setTimingToast("");
    setFeedback(phase === "main" ? "跟着流动的音符，按自己的节奏来弹。" : "只练刚才错过的地方。");

    if (context.state === "running") {
      const secondsPerBeat = beatsToSeconds(1, 60);
      for (let beat = -1; beat < totalBeats; beat += 1) {
        scheduleMetronome(context, transport.startTime + beat * secondsPerBeat, beat % 3 === 0);
      }
    }
    runAnimation(transport);
  }, [runAnimation, targets]);

  useEffect(() => {
    if (autoStartedRef.current) return;
    autoStartedRef.current = true;
    void begin(targets, "main");
  }, [begin, targets]);

  useEffect(() => {
    if (status !== "recovery-prompt" || exitOpen || retryTargets.length === 0) return;
    recoveryTimerRef.current = window.setTimeout(() => {
      void begin(retryTargets, "recovery");
    }, 2100);
    return () => {
      if (recoveryTimerRef.current !== null) window.clearTimeout(recoveryTimerRef.current);
    };
  }, [begin, exitOpen, retryTargets, status]);

  const tap = useCallback((midi = 60) => {
    const transport = transportRef.current;
    if (!transport || status !== "running") return;
    const beat = transport.beat();
    if (beat < 0 || beat >= attemptTotalRef.current) return;
    const tapEvent = { id: `tap-${tapsRef.current.length + 1}`, beat };
    tapsRef.current.push(tapEvent);
    void transport.context?.resume();
    if (transport.context) scheduleMidiTone(transport.context, midi, transport.context.currentTime, 0.28, 0.11);
    setActiveMidi(midi);
    setHitSerial((value) => value + 1);
    if (activeTimerRef.current !== null) window.clearTimeout(activeTimerRef.current);
    activeTimerRef.current = window.setTimeout(() => setActiveMidi(null), 220);
    const nearest = findNearestRhythmTarget(activeTargetsRef.current, beat, matchedRef.current);
    if (!nearest) {
      setTimingToast("再等等");
      setFeedback("再等等，让色块更靠近判定线。");
      if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
      toastTimerRef.current = window.setTimeout(() => setTimingToast(""), 650);
      return;
    }
    matchedRef.current.add(nearest.target.id);
    setMatchedIds(new Set(matchedRef.current));
    const absolute = Math.abs(nearest.delta);
    const nextFeedback = absolute <= 0.14 ? "正好！" : nearest.delta < 0 ? "早了一点" : "晚了一点";
    setTimingToast(nextFeedback);
    setFeedback(nextFeedback);
    if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setTimingToast(""), 650);
  }, [status]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      const isRhythmKey = event.code === "Space" || event.code === "Enter";
      if (!isRhythmKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("button, a, input, textarea, select")) return;
      event.preventDefault();
      tap(60);
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
      setFeedback("练习已暂停，准备好后从这里继续。");
    }
  }

  async function openExitDialog() {
    resumeAfterExitRef.current = status === "running";
    if (status === "running") {
      await transportRef.current?.pause();
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      setStatus("paused");
    }
    setExitOpen(true);
  }

  async function continuePractice() {
    setExitOpen(false);
    if (!resumeAfterExitRef.current) return;
    const transport = transportRef.current;
    if (!transport) return;
    await transport.resume();
    setStatus("running");
    runAnimation(transport);
  }

  const pass = Boolean(result && result.accuracy >= 0.8);
  const accuracyPercent = result ? Math.round(result.accuracy * 100) : 0;
  const finalVisibleTarget = activeTargets.at(-1);
  const visibleAttemptTotal = Math.max(2, (finalVisibleTarget?.beat ?? 0) + (finalVisibleTarget?.durationBeats ?? 1) + 0.5);
  const attemptProgress = Math.max(0, Math.min(1, currentBeat / visibleAttemptTotal));
  const progress = status === "completed"
    ? 1
    : phase === "recovery"
      ? 0.86 + attemptProgress * 0.14
      : attemptProgress * 0.86;
  const showInstruction = status === "booting" || (status === "running" && currentBeat < 0.5);

  return (
    <main className="rhythm-practice-screen" aria-labelledby="lesson-title">
      <div className="immersive-progress" role="progressbar" aria-label="练习进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
        <i style={{ transform: `scaleX(${progress})` }} />
        <b key={hitSerial} className={hitSerial ? "burst" : ""} style={{ left: `${Math.max(2, progress * 100)}%` }} aria-hidden="true" />
      </div>

      <button type="button" className="immersive-exit" aria-label="退出练习" onClick={() => void openExitDialog()}><X size={40} weight="bold" /></button>

      {status !== "recovery-prompt" ? (
        <div className="practice-playfield">
          <h1 id="lesson-title" className={showInstruction ? "practice-instruction visible" : "practice-instruction"}>按自己的节奏来弹</h1>
          <div className="immersive-staff">
            <RhythmLane
              targets={activeTargets}
              currentBeat={currentBeat}
              matchedIds={matchedIds}
              showTimeSignature={showInstruction}
            />
          </div>
          <div className="immersive-piano">
            <VirtualPiano
              activeMidi={activeMidi}
              disabled={status !== "running" || currentBeat < 0}
              hitSerial={hitSerial}
              onNote={(midi) => tap(midi)}
            />
          </div>
          <div key={timingToast} className={timingToast ? "timing-toast visible" : "timing-toast"} aria-hidden={!timingToast}>{timingToast}</div>
        </div>
      ) : (
        <div className="recovery-coach" role="status">
          <img src="/assets/moon-panda-coach.png" alt="月月教练" />
          <div><strong>来重练一下</strong><span>刚才错过的 {retryTargets.length} 个地方</span></div>
        </div>
      )}

      {status === "paused" && !exitOpen ? (
        <button type="button" className="paused-resume" onClick={() => void togglePause()}><Play size={24} weight="fill" />继续练习</button>
      ) : null}

      <button type="button" className={trayOpen ? "edge-handle open" : "edge-handle"} aria-label={trayOpen ? "收起练习控制" : "展开练习控制"} onClick={() => setTrayOpen((value) => !value)}>
        {trayOpen ? <CaretRight size={34} weight="bold" /> : <CaretLeft size={34} weight="bold" />}
      </button>
      <div className={trayOpen ? "practice-tray open" : "practice-tray"} aria-hidden={!trayOpen}>
        <button type="button" onClick={() => void togglePause()}>{status === "paused" ? <Play weight="fill" /> : <Pause weight="fill" />}<span>{status === "paused" ? "继续" : "暂停"}</span></button>
        <button type="button" onClick={() => void begin(targets, "main")}><ArrowCounterClockwise /><span>重来</span></button>
      </div>

      {exitOpen ? (
        <div className="practice-dialog-backdrop">
          <section className="practice-exit-dialog" role="dialog" aria-modal="true" aria-labelledby="exit-title">
            <img src="/assets/moon-panda-coach.png" alt="" />
            <h2 id="exit-title">别走，只差一点就完成了！</h2>
            <div className="dialog-actions">
              <Link href="/" className="dialog-quit">退出</Link>
              <button type="button" onClick={() => void continuePractice()}>继续努力</button>
            </div>
          </section>
        </div>
      ) : null}

      {status === "completed" && result ? (
        <div className="practice-dialog-backdrop completion-backdrop">
          <section className="practice-complete-dialog" role="dialog" aria-labelledby="complete-title">
            <CheckCircle size={54} weight="fill" />
            <div><span>节奏达标率</span><strong>{accuracyPercent}%</strong></div>
            <h2 id="complete-title">{pass ? "稳稳接住了每一个落点" : "再来一遍，手感会更稳"}</h2>
            <p>命中 {Math.min(targets.length, result.matches.length)} / {targets.length} · 多按 {result.extras.length} 次</p>
            <div className="dialog-actions">
              <button type="button" className="dialog-retry" onClick={() => void begin(targets, "main")}><ArrowCounterClockwise size={20} />再练一次</button>
              <Link href="/">完成练习 <ArrowRight size={20} /></Link>
            </div>
          </section>
        </div>
      ) : null}

      <p className="sr-only" aria-live="polite">{feedback}</p>
    </main>
  );
}

export function StageOnePractice({ lessonId }: StageOnePracticeProps) {
  if (lessonId === "B1-02") return SHOW_STATIC_SCORE_REVIEW ? <StaticScoreReview /> : <RhythmLesson />;
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
      <ListenLesson />
      <p className="practice-footnote">第 6–7 小节 · 先听见，再弹出来</p>
    </main>
  );
}
