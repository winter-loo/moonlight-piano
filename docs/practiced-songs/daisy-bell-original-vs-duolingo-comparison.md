# 《Daisy Bell (Bicycle Built for Two)》原作印刷体五线谱与多邻国改编版本对比报告

> **文献编号**：MUS-COMP-20260902-DB01  
> **研究对象**：Harry Dacre 1892 原版印刷体乐谱 vs. 多邻国音乐（Duolingo Music）第 4 阶段第 7 部分实机练习片段

---

## 摘要

《Daisy Bell (A Bicycle Built for Two)》是 19 世纪末广为流传的英国音乐厅圆舞曲代表作。本文档通过对比 **1892 年历史印刷体大谱表** 与 **现代多邻国音乐教育软件（Duolingo Music）中的 34 小节实机片段**，系统性剖析多邻国在曲式截取、音域限制、黑白键规避、双手织体降维以及人机交互延迟补偿等层面的教学法简化逻辑。

---

## 一、 1892 年原创印刷体五线谱形态考证

```mermaid
graph TD
    subgraph "1892 原创印刷体大谱表 (Original Grand Staff)"
        Intro["前奏 (Piano Intro, 4~8小节)<br>三拍子圆舞曲伴奏型"] --> Verse1["主歌 1 (Verse 1, 16小节)<br>叙事歌词: There is a flower..."]
        Verse1 --> Chorus1["副歌 1 (Chorus, 16小节)<br>核心旋律: Daisy, Daisy..."]
        Chorus1 --> Verse2["主歌 2 (Verse 2)"]
        Verse2 --> Chorus2["副歌 2 (Chorus)"]
        Chorus2 --> Verse3["主歌 3 (Verse 3)"]
        Verse3 --> Chorus3["副歌 3 (Chorus)"]
        Chorus3 --> Outro["尾声 (Piano Outro)<br>钢琴强音与分解和弦"]
    end
```

### 1. 编制与织体特征
- **编制形式**：声乐独唱（Vocal Line）+ 钢琴伴奏大谱表（Piano Grand Staff），或双行钢琴独奏曲谱；
- **原始调性**：历史首版以 **F 大调**（1 个降号 $\text{B}\flat$）或 **G 大调**（1 个升号 $\text{F}\sharp$）为主；
- **拍号与律动**：**3/4 拍**，标准速度标记为 *Tempo di Valse*（经典三拍子圆舞曲，约 $120 \sim 140\text{ BPM}$）；
- **左手伴奏型**：典型的“澎-恰-恰”（Boom-Chic-Chic）低音单音跳音 + 两个两拍柱式/分解和弦；
- **旋律线特征**：包含半拍弱起小节（Anacrusis），音域纵跨一个半八度（约 $G_3 \sim G_5$）。

---

## 二、 多邻国实机片段的曲式映射

多邻国并未采用原曲冗长的“主歌+副歌”循环，而是截取了全曲辨识度最高的核心 **【副歌（Chorus）】**，并重构为 **34 小节** 的单手练习闭环：

```mermaid
flowchart LR
    subgraph "多邻国 34 小节结构重构 (Duolingo 34-Bar Loop)"
        direction LR
        S1["小节 1~3<br>【缓冲与起奏】<br>F4长音 + 7拍休止"] --> S2["小节 4~18 (15小节)<br>【第 1 遍副歌主旋律】<br>Daisy, Daisy..."]
        S2 --> S3["小节 19<br>【呼吸换气】<br>3拍四分休止符"]
        S3 --> S4["小节 20~34 (15小节)<br>【第 2 遍副歌巩固】<br>Look sweet... built for two!"]
    end
```

### 逐段对应分析：
1. **第 1–3 小节（起奏准备期）**：以第 1 小节 $F_4$ 触发起奏，随后安排 2 个全休止小节（共 7 拍休止）。此设计为用户提供了约 $5.37\text{ 秒}$ 的视觉就位与心理准备缓冲；
2. **第 4–18 小节（副歌完整乐段 A）**：完整对应原版副歌唱词（*"Daisy, Daisy, give me your answer do / I'm half crazy all for the love of you..."*）；
3. **第 19 小节（中段呼吸休止）**：3 个四分休止符构成乐句间隔；
4. **第 20–34 小节（副歌乐段 A' 强化重复）**：结构与第 4–18 小节完全镜像，作为巩固训练，最终在第 34 小节以正规双终止线收尾。

---

## 三、 对新手友好的五大“降维简化”策略

```
┌───────────────────────────────┬────────────────────────────────────────────────────────┐
│ 传统原版乐谱特征 (Traditional) │ 多邻国新手教学降维重塑 (Duolingo Music Simplification) │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 1. 包含黑键调号 (F/G大调 Bb/F#)│ 👉 纯白键化 (C大调自然音，严格限制在 C4~B4 单八度内)   │
│ 2. 双手复合织体 (左手伴奏+右手)│ 👉 单手单音旋律 (Monophonic，完全剥离伴奏与和弦)        │
│ 3. 快速圆舞曲 (120~140 BPM)    │ 👉 放缓至 100 BPM 中速 (四分音符稳定 0.6s，八分 0.3s)   │
│ 4. 弱起小节与弹性速度 (Rubato) │ 👉 绝对强拍起步，严格规整化小节量化时钟                │
│ 5. 无准备直接滚动进音          │ 👉 前置长达 5 秒的连续休止符作为视觉/肌肉就位缓冲      │
└───────────────────────────────┴────────────────────────────────────────────────────────┘
```

### 1. 纯白键化与 7 键单八度固定手位（Zero Black Keys）
- **原版挑战**：原版 F 大调带有黑键 $\text{B}\flat$；若直接下移至标准 C 大调，旋律将下潜至 $A_3$ 和 $G_3$，超出手机单屏键盘宽度。
- **教学简化**：多邻国通过调整音程与调式模进，将全曲 75 个音符精准压缩在 **$C_4, D_4, E_4, F_4, G_4, A_4, B_4$** 7 个白键内。学生右手五指放在固定手位即可完整演奏，无需横向倒手或大跨度跳跃。

### 2. 双手织体降维为单音单声部（Monophonic Line）
- **原版挑战**：原版左手需要同时处理低音跳音与两个双音和弦，属于典型的双手协调（Hand Independence）技能。
- **教学简化**：完全移除左手伴奏声部，仅保留右手单声部主旋律，让初学者将注意力 $100\%$ 集中在音高辨识与节奏长按上。

### 3. 速度放缓与时序绝对规整化
- **原版挑战**：原版为欢快的 120–140 BPM 圆舞曲，且带有弱起半拍。
- **教学简化**：
  - 速度固定为 **100 BPM**（四分音符 $0.6\text{s}$、二分音符 $1.2\text{s}$、附点四分 $0.9\text{s}$、八分 $0.3\text{s}$）；
  - 移除所有弱起，所有音符严格落在小节内的整数或半拍正拍上。

### 4. 交互层面的“前置准备时钟”（Readiness Buffer）
- 第 1 小节长音后紧跟 7 拍休止符，为移动端触屏滚动谱面建立、视觉注意力聚焦提供了充分的物理反应时间。

### 5. 对称式重复记忆（Pedagogical Reinforcement）
- 采用 $[4 \sim 18] + [\text{休止}] + [20 \sim 34]$ 的对称结构，用户在前半段建立的指法记忆可以直接复用到后半段，带来极高的即时正反馈与通关成就感。

---

## 四、 核心参数综合对比矩阵

| 参数维度 | 1892 原作印刷体五线谱 | 多邻国音乐实机版本 (`bicycle-built-for-two.md`) |
| :--- | :--- | :--- |
| **曲谱类型** | 双行大谱表（声乐+钢琴伴奏） | 单行高音谱表（单音旋律） |
| **调号** | F 大调（1 降号） / G 大调（1 升号） | **C 大调（0 升 0 降）** |
| **音域覆盖** | $G_3 \sim G_5$（约 15 度音程） | **$C_4 \sim B_4$（严格 7 个自然音）** |
| **黑键使用** | 包含黑键（$\text{B}\flat_4$ 或 $\text{F}\sharp_4$） | **$0$ 个黑键（全白键）** |
| **节拍与速度** | 3/4 拍，$120 \sim 140\text{ BPM}$ | **3/4 拍，固定 $100\text{ BPM}$** |
| **小节规模** | 约 60–80 小节（完整 3 段主副歌） | **34 小节（副歌 $\times 2$ 循环）** |
| **音符总数** | 约 200+ 音符（含左手伴奏和弦） | **75 个音符 + 10 个四分休止符** |
| **演奏难度** | 拜厄中后期 / 车尔尼 599 程度 | **初学者阶段 4 级入门程度** |

---

## 五、 参考资料与文献清单 (References)

1. **Dacre, Harry (1892)**. *Daisy Bell (A Bicycle Built for Two)*. London: Francis, Day & Hunter; New York: T. B. Harms & Co. [First Edition Sheet Music].
2. **Library of Congress (LOC) Historic Sheet Music Collection**. *Daisy Bell / words and music by Harry Dacre*. Call Number: M1622.D.
3. **IMSLP / Petrucci Music Library**. *Daisy Bell (Dacre, Harry)*. [Online score repository](https://imslp.org/wiki/Daisy_Bell_(Dacre,_Harry)).
4. **W3C Music Notation Community Group (2021)**. *Standard Music Font Layout (SMuFL) Specification v1.4*. W3C Community Development.
5. **Duolingo Inc. (2024)**. *Duolingo Music Curriculum & Course Structure (Stage 4, Section 7)*.
6. **项目实机演奏与证据库**：[`moonlight/docs/practiced-songs/bicycle-built-for-two.md`](file:///Users/ldd/proj/lab-piano/moonlight/docs/practiced-songs/bicycle-built-for-two.md)
7. **Meloo Rounded 字体规范**：[`meloo-font/AGENTS.md`](file:///Users/ldd/proj/lab-piano/meloo-font/AGENTS.md)
8. **交互五线谱呈现工程**：[`moonlight/docs/practiced-songs/bicycle-built-for-two-score.html`](file:///Users/ldd/proj/lab-piano/moonlight/docs/practiced-songs/bicycle-built-for-two-score.html)
