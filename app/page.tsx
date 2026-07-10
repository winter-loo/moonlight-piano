"use client";

import { useState } from "react";
import {
  ArrowRight, CheckCircle, Flame, Hand, House, LockKey, Medal, MusicNote,
  PianoKeys, PlayCircle, SpeakerHigh, Target, Trophy, UserCircle,
} from "@phosphor-icons/react";

const nav = [
  ["学习之旅", House], ["曲库", MusicNote], ["练习室", PlayCircle], ["成就", Trophy], ["我的", UserCircle],
] as const;

const goals = [
  ["练习时长 30 分钟", "22 / 30", 73], ["完整演奏 2 遍", "1 / 2", 50], ["正确率达到 80%", "76% / 80%", 95],
];

export default function Home() {
  const [activeNav, setActiveNav] = useState("学习之旅");
  const [isPlaying, setIsPlaying] = useState(false);
  const [tempo, setTempo] = useState(72);
  const [hand, setHand] = useState<"右手" | "左手">("右手");
  const [notice, setNotice] = useState("准备开始今天的练习");

  function togglePractice() {
    setIsPlaying((previous) => !previous);
    setNotice(isPlaying ? "练习已暂停，可以从这一小节继续" : "正在跟随月光节拍练习…");
  }

  return (
    <main className="moonlight-app">
      <aside className="left-nav" aria-label="月光琴房导航">
        <div className="wordmark"><span className="crescent" aria-hidden="true">◖</span><span>月光琴房</span></div>
        <p className="tagline">学钢琴 · 更动听</p>
        <div className="nav-list">
          {nav.map(([label, Icon]) => <button key={label} className={activeNav === label ? "nav-choice selected" : "nav-choice"} onClick={() => { setActiveNav(label); setNotice(`已切换到${label}`); }}><Icon weight="fill" size={25} /><span>{label}</span></button>)}
        </div>
        <img className="sidebar-still-life" src="/assets/sidebar-vase-candle.png" alt="烛光与花枝" />
        <p className="sidebar-quote">在每一个音符里<br />遇见更好的自己 <MusicNote size={16} weight="fill" /></p>
      </aside>

      <section className="app-stage">
        <header className="hero-scene">
          <div className="hero-copy"><h1>梦中的婚礼</h1><p>从零开始，30天学会弹奏</p></div>
          <img src="/assets/moonlit-grand-piano.png" alt="月光下的三角钢琴" className="hero-piano" />
        </header>

        <div className="dashboard-grid">
          <section className="panel course-panel">
            <header className="panel-title"><span>学习进度地图</span><small>第 3 / 7 章</small></header>
            <div className="path-map"><img src="/assets/learning-path.png" alt="七阶段学习进度路径" />
              <button className="course-stop stop-one" onClick={() => setNotice("初识旋律：已完成")}>1</button>
              <button className="course-stop stop-two" onClick={() => setNotice("右手入门：已完成")}>2</button>
              <button className="course-stop stop-three" onClick={() => setNotice("左手伴奏：当前练习")}>3</button>
              <button className="course-stop stop-four" onClick={() => setNotice("双手合奏将在下一章节解锁")}><LockKey size={15} /></button>
            </div>
            <div className="lesson-labels"><span>初识旋律<em>★ ★ ★</em></span><span>右手入门</span><span>左手伴奏</span><span>双手合奏</span></div>
            <div className="lesson-labels lower"><span>情感表达</span><span>速度提升</span><span>完整演奏</span><span className="gold">舞台时刻</span></div>
          </section>

          <section className="panel practice-panel">
            <header className="panel-title"><span>当前练习 <b>第1节 · 初识旋律</b></span><div className="tempo-readout">♩ = {tempo} <button onClick={() => setNotice("已打开示范演奏")}>示范</button></div></header>
            <button className={isPlaying ? "score-image score-active" : "score-image"} onClick={togglePractice} aria-label="播放或暂停乐谱"><img src="/assets/practice-score.png" alt="梦中的婚礼练习乐谱" /></button>
            <button className="keyboard-image" onClick={() => setNotice(`正在练习${hand}音区，跟随发光琴键`)} aria-label="播放琴键提示"><img src="/assets/glowing-keyboard.png" alt="发光的钢琴键盘" /></button>
            <footer className="practice-footer"><button className="icon-control" onClick={() => setNotice("音轨已静音或恢复")}><SpeakerHigh size={20} />音轨</button><div className="hand-switch"><button className={hand === "左手" ? "hand active" : "hand"} onClick={() => setHand("左手")}><Hand size={20} />左手</button><button className={hand === "右手" ? "hand active" : "hand"} onClick={() => setHand("右手")}><Hand size={20} />右手</button></div><button className="icon-control" onClick={() => setNotice("已隐藏琴键提示")}><PianoKeys size={20} />隐藏</button></footer>
          </section>

          <aside className="right-column">
            <section className="panel goal-panel"><header className="panel-title"><span>今日目标</span><Target size={30} weight="duotone" /></header>{goals.map(([label, value, percent]) => <div className="goal-row" key={label}><div><span><CheckCircle size={16} weight="fill" />{label}</span><b>{value}</b></div><div className="goal-track"><i style={{ width: `${percent}%` }} /></div></div>)}</section>
            <section className="panel streak-panel"><div className="streak-item"><Flame weight="fill" size={37} /><div><b>7 <small>天</small></b><span>连续练习</span></div></div><div className="streak-divider" /><div className="streak-item"><Medal weight="fill" size={35} /><div><b>1280</b><span>总经验值</span></div></div><div className="level-row"><b>Lv.4</b><div><i /></div><small>1280 / 2000</small></div></section>
            <section className="panel stability-panel"><header className="panel-title"><span>速度稳定性</span><small>近7次练习</small></header><img src="/assets/stability-chart.png" alt="最近七次练习的速度稳定性曲线" className="stability-image" /><div className="average">平均 <b>78%</b></div></section>
            <section className="encouragement"><MusicNote size={35} weight="fill" /><p>坚持的每一天，<br />都是向舞台更近一步。</p></section>
          </aside>
        </div>
        <div className="bottom-bar"><p aria-live="polite">{notice}</p><div className="stage-lines" /><button className={isPlaying ? "start-button running" : "start-button"} onClick={togglePractice}>{isPlaying ? "暂停练习" : "开始练习"}<ArrowRight size={26} weight="bold" /></button></div>
      </section>
    </main>
  );
}
