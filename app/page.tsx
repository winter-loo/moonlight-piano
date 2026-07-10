"use client";

import { useMemo, useState } from "react";

const lessons = [
  { number: 1, title: "初识旋律", state: "done" },
  { number: 2, title: "右手入门", state: "done" },
  { number: 3, title: "左手伴奏", state: "current" },
  { number: 4, title: "双手合奏", state: "locked" },
  { number: 5, title: "情感表达", state: "locked" },
  { number: 6, title: "速度提升", state: "locked" },
  { number: 7, title: "完整演奏", state: "locked" },
];

const keys = ["C", "D", "E", "F", "G", "A", "B", "C", "D", "E", "F", "G", "A", "B"];
const activeNotes = ["E", "G", "C"];

export default function Home() {
  const [started, setStarted] = useState(false);
  const [note, setNote] = useState("E");
  const [speed, setSpeed] = useState(72);
  const [activeNav, setActiveNav] = useState("学习之旅");
  const currentHint = useMemo(
    () => (started ? `正在聆听：${note}，保持手腕放松` : "准备好后，让第一颗音符亮起来"),
    [note, started],
  );

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">◖</span><span>月光琴房</span></div>
        <p className="brand-subtitle">学钢琴 · 更动听</p>
        <nav aria-label="主导航">
          {["学习之旅", "曲库", "练习室", "成就", "我的"].map((item, i) => (
            <button key={item} onClick={() => setActiveNav(item)} className={`nav-item ${activeNav === item ? "active" : ""}`}>
              <span>{["✦", "♫", "▣", "♜", "●"][i]}</span>{item}
            </button>
          ))}
        </nav>
        <div className="sidebar-quote">在每一个音符里，<br />遇见更好的自己 ♫</div>
      </aside>

      <section className="workspace">
        <header className="hero">
          <div>
            <p className="eyebrow">从零开始 · 30 天学会弹奏</p>
            <h1>梦中的婚礼</h1>
            <p className="hero-copy">把每一次练习，变成走向舞台的一小步。</p>
          </div>
          <div className="moon-scene" aria-hidden="true"><span className="moon" /><span className="piano-shape">♩</span></div>
        </header>

        <div className="content-grid">
          <section className="panel journey-panel">
            <div className="panel-heading"><span>学习进度地图</span><small>第 3 / 7 章</small></div>
            <div className="lesson-path">
              {lessons.map((lesson, index) => (
                <div key={lesson.number} className={`lesson ${lesson.state}`}>
                  <button aria-label={lesson.title} className="lesson-dot" onClick={() => lesson.state !== "locked" && setStarted(true)}>
                    {lesson.state === "done" ? "✓" : lesson.state === "locked" ? "·" : lesson.number}
                  </button>
                  <span>{lesson.title}</span>
                  {index < lessons.length - 1 && <i className="path-line" />}
                </div>
              ))}
            </div>
            <div className="journey-caption">你已走过 2 个章节，下一站：<b>左手伴奏</b></div>
          </section>

          <section className="panel practice-panel">
            <div className="panel-heading"><span>当前练习 <em>第 3 章 · 左手伴奏</em></span><span className="tempo">♩ = {speed}</span></div>
            <div className="score-card">
              <div className={`playhead ${started ? "playing" : ""}`} />
              <div className="clef">𝄞</div>
              <div className="staff"><i /><i /><i /><i /><i /></div>
              <div className="notes">♪　♫　♪　♩　♫　♪　♩</div>
              <div className="fingerings">5　3　1　2　3　1　5</div>
            </div>
            <div className="piano-wrap">
              <div className="piano-label"><span>虚拟钢琴</span><small>{currentHint}</small></div>
              <div className="keyboard" role="group" aria-label="虚拟钢琴键盘">
                {keys.map((key, index) => {
                  const lit = activeNotes.includes(key) && index < 7;
                  return <button key={`${key}-${index}`} onClick={() => { setNote(key); setStarted(true); }} className={`white-key ${lit && started ? "lit" : ""}`}><span>{key}</span>{[0, 1, 3, 4, 5, 7, 8, 10, 11].includes(index) && <i className="black-key" />}</button>;
                })}
              </div>
            </div>
            <div className="practice-controls">
              <button className="subtle" onClick={() => setSpeed((value) => Math.max(50, value - 4))}>− 慢一点</button>
              <button className="main-action" onClick={() => setStarted((value) => !value)}>{started ? "暂停练习" : "开始练习"}<span>→</span></button>
              <button className="subtle" onClick={() => setSpeed((value) => Math.min(120, value + 4))}>快一点 +</button>
            </div>
          </section>

          <aside className="right-rail">
            <section className="panel goal-panel">
              <div className="panel-heading"><span>今日目标</span><span>◎</span></div>
              {[['练习时长 30 分钟', '22 / 30'], ['完整演奏 2 遍', '1 / 2'], ['正确率达到 80%', '76 / 80']].map(([label, value]) => (
                <div className="goal" key={label}><div><span>◉</span>{label}<b>{value}</b></div><progress value={parseInt(value, 10)} max={parseInt(value.split('/ ')[1], 10)} /></div>
              ))}
            </section>
            <section className="panel stats-panel">
              <div className="stat-row"><span>🔥 <b>7</b> 天<small>连续练习</small></span><span>✦ <b>1280</b><small>总经验值</small></span></div>
              <div className="level"><span>Lv.4</span><div><i /></div><small>1280 / 2000</small></div>
            </section>
            <section className="panel chart-panel"><div className="panel-heading"><span>速度稳定性</span><small>近 7 次练习</small></div><div className="chart" aria-label="速度稳定性：平均 78%"><div className="chart-grid" /><div className="chart-line"><i /><i /><i /><i /><i /><i /><i /></div><span>平均 <b>78%</b></span></div></section>
            <section className="encourage">✧ 坚持的每一天，<br />都是向舞台更近一步。</section>
          </aside>
        </div>
      </section>
    </main>
  );
}
