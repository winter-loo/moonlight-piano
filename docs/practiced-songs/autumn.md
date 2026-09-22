# Autumn – 奥斯卡版本

## 基本信息

- 应用：Duolingo Music（版本 6.95.4-china，2026-09-04 更新）
- 设备：OPPO PHJ110（Android 13，1612×720 横屏）
- 课程位置：第 4 阶段、第 1 部分
- 挑战类型：最终终极挑战（`弹奏Autumn`），连续谱面演奏
- 应用显示标题：Autumn
- 版本：奥斯卡版本（Oscar version）
- 谱号：高音谱号
- 拍号：4/4
- 调号：一个降号 B♭；音集与 F 大调相容。谱面上的所有 B 一律按 B♭ 演奏，键盘上该黑键直接标注 `B♭`
- 临时升降号：未见调号以外的临时升降号
- 有效音域：F4–D5
- 完成结果：1000 分、三颗星；音高 100%、节奏 52%、20 经验；结算页显示「成功刷新纪录！」（挑战前 `最高记录 0`）

标题与版本证据：[终极挑战标题卡](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-1-capture/start-card.png)；谱号、拍号、调号与键盘证据：[可停顿练习起始画面](../../outputs/duolingo-stage4-section1-autumn/practice/ready.png)；完成证据：[1000 分三颗星结算页](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-2-candidate/final-three-stars.png)。

## 时值与演奏参数

- 正式谱面为 13 个 4/4 小节，共 52 拍、63 个有效音符。
- 八分音符 50、四分音符 8、二分音符 5；音符合计 43 拍，休止符合计 9 拍。
- 音高计数：A4×38、B♭4×15、G4×6、C5×2、D5×1、F4×1。
- 谱面滚动速度实测 179.55 px/s，谱面间距 144 px/拍（八分音符间距 72 px）。
- 最终采用四分音符 802.03ms、74.81 BPM。
- `score_start_delay_ms=0`：本课程的谱面时钟与起奏按键几乎同时开始，与 Musette 的 275ms 不同。
- `input_advance_ms=10.0`，由设备 ACK 稳态延迟实测得出（首次注入含 JVM 预热 333ms，稳态 10.3ms）。

记号：`e`=八分音符，`q`=四分音符，`h`=二分音符，`Rq`=四分休止，`Rh`=二分休止，`R3`=三拍休止，`Rw`=全小节休止。

## 完整谱面

| 小节 | 事件 |
|---:|---|
| 1 | A4(q), R3 |
| 2 | Rw |
| 3 | A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e) |
| 4 | A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e) |
| 5 | A4(q), B♭4(e), A4(e), G4(h) |
| 6 | A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e) |
| 7 | A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e) |
| 8 | A4(q), B♭4(e), A4(e), G4(h) |
| 9 | A4(e), A4(e), A4(e), C5(e), D5(h) |
| 10 | G4(e), G4(e), G4(e), B♭4(e), C5(h) |
| 11 | A4(e), A4(e), A4(e), B♭4(e), A4(e), A4(e), A4(e), B♭4(e) |
| 12 | A4(e), A4(e), A4(e), B♭4(e), A4(q), B♭4(e), G4(e) |
| 13 | F4(h), Rh |

第 1 小节的 A4 是起奏音：画面提示「在琴键上弹 A 开始」，按下后谱面才开始滚动。第 1–2 小节其余部分为休止，第 3 小节（第 8 拍）才进入连续谱面。

曲式：第 3–4 小节陈述动机，第 5 小节落到 G4；第 6–7 小节原样反复，第 8 小节再次落到 G4；第 9 小节上行至 D5，第 10 小节以 G4 音型答句落到 C5；第 11–12 小节回到动机，第 13 小节收在主音 F4。

## 纯音符顺序

`A4(q), A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e), A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e), A4(q), B♭4(e), A4(e), G4(h), A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e), A4(e), A4(e), A4(e), B♭4(e), A4(q), A4(e), B♭4(e), A4(q), B♭4(e), A4(e), G4(h), A4(e), A4(e), A4(e), C5(e), D5(h), G4(e), G4(e), G4(e), B♭4(e), C5(h), A4(e), A4(e), A4(e), B♭4(e), A4(e), A4(e), A4(e), B♭4(e), A4(e), A4(e), A4(e), B♭4(e), A4(q), B♭4(e), G4(e), F4(h)`

## 琴键坐标

本挑战使用 `autumn-f4` profile。坐标以 1612×720 横屏画面为基准，由本课程自己的琴键边界重新测量：白键取相邻分隔线中点，黑键取键帽中心。

| 音高 | x | y | 本曲使用 |
|---|---:|---:|:---:|
| F4 | 172 | 600 | 是 |
| G♭4 | 234 | 475 | 否 |
| G4 | 293 | 600 | 是 |
| A♭4 | 355 | 475 | 否 |
| A4 | 414 | 600 | 是 |
| B♭4 | 476 | 475 | 是 |
| B4 | 535 | 600 | 否 |
| C5 | 674 | 600 | 是 |
| D♭5 | 734 | 475 | 否 |
| D5 | 793 | 600 | 是 |
| E♭5 | 855 | 475 | 否 |
| E5 | 913 | 600 | 否 |
| F5 | 1053 | 600 | 否 |
| G♭5 | 1113 | 475 | 否 |
| G5 | 1172 | 600 | 否 |
| A♭5 | 1234 | 475 | 否 |
| A5 | 1293 | 600 | 否 |
| B♭5 | 1355 | 475 | 否 |
| B5 | 1413 | 600 | 否 |

五线谱几何：五条谱线位于 y=182.5 / 220.5 / 258.5 / 296.5 / 334.5，线距 38px，即每个音级 19px；判定线位于 x≈402–408。

## 曲尾审计与停止边界

- `last_valid_event_index=62`
- `last_valid_pitch=F4`
- 最后有效音符：beat 48 按下，持续 2 拍，在 beat 50 释放
- `stop_after_beat=50`；释放 F4 后进入最后二拍休止，关闭 `playback_gate`
- 本次演奏共发送 126 个动作（63 个 DOWN + 63 个 UP），触及的最大事件索引为 62，与审计边界一致；曲尾没有任何多余输入。
- 设备 ACK 漂移：均值 18.67ms、最小 1.76ms、最大 165.96ms（最大值出现在首个音符的注入预热）。

停止闸门由 `PlaybackGate` 执行，`timing-log.json` 记录 `playback_gate_closed_reason="frozen plan exhausted"`、`playback_gate_close_was_planned=true`，即以计划内收尾结束，最后音符按完整时值释放。

## 取证文件

- [终极挑战标题卡（最高记录 0）](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-1-capture/start-card.png)
- [第 2 遍完整 H.264 原流](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-2-candidate/full-stream.h264)
- [第 2 遍封装后的 MP4](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-2-candidate/full-stream.mp4)
- [设备时序日志](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-2-candidate/performance/timing-log.json)
- [播放器参数与动作记录](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-2-candidate/player.stdout.json)
- [1000 分三颗星结算页](../../outputs/duolingo-stage4-section1-autumn/ultimate/pass-2-candidate/final-three-stars.png)
- [冻结事件账本（63 事件）](../../outputs/duolingo-stage4-section1-autumn/autumn-frozen-plan.json)
- [可停顿练习起始画面](../../outputs/duolingo-stage4-section1-autumn/practice/ready.png)
- [可停顿练习 100% 完成页](../../outputs/duolingo-stage4-section1-autumn/practice/practice-complete-100pct.png)
- [练习逐帧读谱日志 A](../../outputs/duolingo-stage4-section1-autumn/practice/practice-pass-a-log.json)
- [练习逐帧读谱日志 B](../../outputs/duolingo-stage4-section1-autumn/practice/practice-pass-b-log.json)
- [三遍预算状态](../../outputs/duolingo-stage4-section1-autumn/attempt-state.json)

## 记录说明

- 谱面来自倒数第二个可停顿练习的逐帧读谱：把每一帧的谱面读数按滚动位移拼接成全局账本（144 px/拍），再用"相邻音符拍距等于前一音符时值"闭合每个小节。该练习最终以 100%（超级棒）完成。
- 终极挑战的 `音高 100%` 独立验证了这份谱面：63 个音符的音高全部判定正确。
- `节奏 52%` 说明相位仍有系统性偏差。事后统计 ACK 漂移均值为 18.67ms，而本次只补偿了 10.0ms；若追求更高节奏分，应把 `input_advance_ms` 提到约 18–19ms 再跑一遍。三颗星与 1000 分已达成完成标准，故未继续消耗第三遍预算。
- 调号陷阱：`analyze_staff_png` 返回的是五线谱位置（`B4`），必须再经调号拼写成 `B♭4`。首次自动演奏正是因为按了白键 B 而卡住，画面同时用粉色音符和高亮 `B♭` 琴键提示了正确音。
- 输入方式：本挑战对 `adb shell input swipe`（同点长按）无反应，但接受 `adb shell input tap` 与 `CodexInputBridge` 注入的 MotionEvent。正式演奏使用输入桥。
- 第 1 遍（pass-1-capture）只用于测量滚动速度与相位，没有演奏，未取得成绩；其录像中大部分时间是等待起奏与一次「加时 15 分钟」弹窗，只有末段拍到滚动。第 2 遍即取得三颗星。
