"use client";

import { useState } from "react";
import {
  ArrowRight,
  GameController,
  Hand,
  LockKey,
  MusicNote,
  MusicNotes,
  PianoKeys,
  PlayCircle,
  SpeakerHigh,
  Trophy,
  UserCircle,
} from "@phosphor-icons/react";

const navItems = [
  ["学习之旅", GameController],
  ["曲库", MusicNotes],
  ["练习室", PlayCircle],
  ["成就", Trophy],
  ["我的", UserCircle],
] as const;

const goals = [
  ["练习时长 30 分钟", "22 / 30", 73],
  ["完整演奏 2 遍", "1 / 2", 50],
  ["正确率达到 80%", "76% / 80%", 95],
] as const;

const mapStops = [
  ["初识旋律", "已完成初识旋律", "map-stop-1"],
  ["右手入门", "已完成右手入门", "map-stop-2"],
  ["左手伴奏", "正在练习左手伴奏", "map-stop-3"],
  ["双手合奏", "双手合奏将在下一章节解锁", "map-stop-4"],
  ["情感表达", "情感表达尚未解锁", "map-stop-5"],
  ["速度提升", "速度提升尚未解锁", "map-stop-6"],
  ["完整演奏", "完整演奏尚未解锁", "map-stop-7"],
] as const;

export default function Home() {
  const [activeNav, setActiveNav] = useState("学习之旅");
  const [isPlaying, setIsPlaying] = useState(false);
  const [tempo, setTempo] = useState(72);
  const [hand, setHand] = useState<"左手" | "右手">("右手");
  const [notice, setNotice] = useState("准备开始今天的练习");

  function togglePractice() {
    setIsPlaying((playing) => {
      setNotice(playing ? "练习已暂停，可以从当前小节继续" : "正在跟随月光节拍练习…");
      return !playing;
    });
  }

  return (
    <main className="moonlight-app">
      <aside className="left-nav" aria-label="月光琴房导航">
        <img className="brand-art" src="/assets/reference-brand.png" alt="月光琴房，学钢琴，更动听" />

        <nav className="nav-list" aria-label="主要功能">
          {navItems.map(([label, Icon]) => (
            <button
              key={label}
              type="button"
              className={activeNav === label ? `nav-choice selected${label === "学习之旅" ? " reference-selected" : ""}` : "nav-choice"}
              aria-current={activeNav === label ? "page" : undefined}
              onClick={() => {
                setActiveNav(label);
                setNotice(`已切换到${label}`);
              }}
            >
              <Icon size={24} weight="fill" aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <img className="sidebar-art" src="/assets/reference-sidebar-still-life.png" alt="月光琴房中的花枝、花瓶与烛光" />
        <p className="sidebar-quote">在每一个音符里<br />遇见更好的自己 <MusicNote size={15} weight="fill" aria-hidden="true" /></p>
      </aside>

      <section className="app-stage">
        <header className="hero-scene">
          <img className="hero-copy-art" src="/assets/reference-hero-copy.png" alt="梦中的婚礼，从零开始，30天学会弹奏" />
          <h1 className="sr-only">梦中的婚礼</h1>
          <img className="hero-piano" src="/assets/reference-hero-piano.png" alt="月色窗景中的三角钢琴" />
        </header>

        <div className="dashboard-grid">
          <section className="panel course-panel" aria-labelledby="course-title">
            <img className="course-header-art" src="/assets/reference-course-header.png" alt="" aria-hidden="true" />
            <h2 id="course-title" className="sr-only">学习进度地图</h2>
            <img className="course-map-art" src="/assets/reference-learning-map.png" alt="从初识旋律到舞台时刻的七阶段学习路线" />
            <div className="map-hotspots">
              {mapStops.map(([label, message, className]) => (
                <button key={label} type="button" className={`map-hotspot ${className}`} aria-label={label} onClick={() => setNotice(message)}>
                  {label === "双手合奏" ? <LockKey size={15} aria-hidden="true" /> : null}
                </button>
              ))}
            </div>
          </section>

          <section className="panel practice-panel" aria-labelledby="practice-title">
            <img className="practice-header-art" src="/assets/reference-practice-header.png" alt="" aria-hidden="true" />
            <header className="panel-title practice-heading">
              <div><h2 id="practice-title">当前练习</h2><span className="lesson-chip">第1节&nbsp; 初识旋律</span></div>
              <div className="tempo-control">
                <button type="button" aria-label="切换节拍速度" onClick={() => { setTempo((value) => value === 72 ? 76 : 72); setNotice("节拍速度已调整"); }}><MusicNote size={16} weight="fill" aria-hidden="true" /><span>= {tempo}</span></button>
                <button type="button" className="demo-button" onClick={() => setNotice("正在播放示范演奏")}>示范</button>
              </div>
            </header>

            <button type="button" className={isPlaying ? "score-button active" : "score-button"} onClick={togglePractice} aria-label="播放或暂停练习乐谱">
              <img src="/assets/reference-practice-score.png" alt="梦中的婚礼双手练习乐谱" />
            </button>

            <button type="button" className="keyboard-button" onClick={() => setNotice(`正在练习${hand}音区`)} aria-label="播放琴键提示">
              <img src="/assets/reference-keyboard.png" alt="高亮当前音符的钢琴键盘" />
            </button>

            <img className="practice-footer-art" src="/assets/reference-practice-footer.png" alt="" aria-hidden="true" />
            <footer className="practice-footer">
              <button type="button" className="icon-control" onClick={() => setNotice("音轨已静音或恢复")}><SpeakerHigh size={21} aria-hidden="true" /><span>音轨</span></button>
              <div className="hand-switch" aria-label="练习手部">
                <button type="button" aria-pressed={hand === "左手"} className={hand === "左手" ? "hand active" : "hand"} onClick={() => { setHand("左手"); setNotice("已切换到左手练习"); }}><Hand size={22} aria-hidden="true" /><span>左手</span></button>
                <button type="button" aria-pressed={hand === "右手"} className={hand === "右手" ? "hand active" : "hand"} onClick={() => { setHand("右手"); setNotice("已切换到右手练习"); }}><Hand size={22} aria-hidden="true" /><span>右手</span></button>
              </div>
              <button type="button" className="icon-control keyboard-toggle" onClick={() => setNotice("琴键提示已隐藏或显示")}><PianoKeys size={20} aria-hidden="true" /><span>隐藏</span></button>
            </footer>
          </section>

          <aside className="right-column" aria-label="学习数据">
            <section className="exact-card-panel goal-panel">
              <img src="/assets/reference-goals-card.png" alt="今日目标：练习22分钟，完整演奏1遍，正确率76%" />
              <h2 className="sr-only">今日目标</h2>
              {goals.map(([label, , percent]) => <div key={label} className="sr-only" role="progressbar" aria-label={label} aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} />)}
            </section>

            <section className="exact-card-panel streak-panel">
              <img src="/assets/reference-streak-card.png" alt="连续练习7天，总经验值1280，等级4" />
              <div className="sr-only" role="progressbar" aria-label="等级经验" aria-valuenow={1280} aria-valuemin={0} aria-valuemax={2000} />
            </section>

            <section className="exact-card-panel stability-panel">
              <img src="/assets/reference-stability-card.png" alt="最近七次练习的速度稳定性曲线，平均百分之七十八" />
              <h2 className="sr-only">速度稳定性</h2>
            </section>

            <img className="encouragement-art" src="/assets/reference-encouragement.png" alt="坚持的每一天，都是向舞台更近一步" />
          </aside>
        </div>

        <div className="bottom-bar">
          <img className="wave-left" src="/assets/reference-bottom-wave-left.png" alt="" aria-hidden="true" />
          <img className="wave-right" src="/assets/reference-bottom-wave-right.png" alt="" aria-hidden="true" />
          <p className="sr-only" aria-live="polite">{notice}</p>
          <button type="button" aria-label={isPlaying ? "暂停练习" : "开始练习"} className={isPlaying ? "start-button running" : "start-button"} onClick={togglePractice}>
            <span>{isPlaying ? "暂停练习" : "开始练习"}</span><ArrowRight size={28} weight="bold" aria-hidden="true" />
          </button>
        </div>
      </section>
    </main>
  );
}
