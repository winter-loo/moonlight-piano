# Musette In C Major – 奥斯卡版本

## 基本信息

- 应用：Duolingo Music
- 设备：OPPO PHJ110
- 课程位置：第 4 阶段、第 14 部分
- 挑战类型：最终终极挑战，连续谱面演奏
- 应用显示标题：Musette In C Major
- 版本：奥斯卡版本（Oscar version）
- 谱号：高音谱号
- 拍号：4/4
- 调号：B♭、E♭ 两个降号；实际谱面音集与 B♭ 大调/G 小调相容。标题虽然包含 “In C Major”，仍以画面显示的两个降号记录实际演奏音高。
- 临时升降号：未见调号以外的临时升降号
- 有效音域：G4–F5
- 完成结果：1000 分、三颗星；音高 100%、节奏 99%、20 经验

标题与版本证据：[终极挑战标题卡](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-5-phase-corrected/start-card.png)；谱号、拍号、调号和键盘证据：[起奏画面](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-7-two-anchor/ready.png)；完成证据：[1000 分三颗星结算页](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-7-two-anchor/final-three-stars.png)。

## 时值与演奏参数

- 正式谱面为 18 个 4/4 小节，共 72 拍、69 个有效音符。
- 八分音符 24、四分音符 42、二分音符 3；音符合计 60 拍，休止符合计 12 拍。
- 音高计数：G4×2、A4×6、B♭4×9、C5×20、D5×10、E♭5×8、F5×14。
- 冻结计划初始测量为四分音符 669.8ms、89.579 BPM；最终双锚点校准采用四分音符 661.9594ms、90.64 BPM。
- 最终名义时值：八分音符 330.9797ms、四分音符 661.9594ms、二分音符 1323.9188ms。
- `score_start_delay_ms=275`，只作用于第 1 个及后续连续谱面音符；`input_advance_ms=20.5`，用于补偿设备输入确认延迟。第 0 个高音 D 使用独立起奏时钟。

记号：`e`=八分音符，`q`=四分音符，`h`=二分音符，`Re`=八分休止，`Rq`=四分休止，`Rh`=二分休止，`R3`=三拍休止，`Rw`=全小节休止。

## 完整谱面

| 小节 | 事件 |
|---:|---|
| 1 | D5(q), R3 |
| 2 | Rw |
| 3 | F5(q), Rq, E♭5(e), D5(e), C5(q) |
| 4 | F5(q), Rq, E♭5(e), D5(e), C5(q) |
| 5 | D5(e), E♭5(e), F5(q), E♭5(q), D5(q) |
| 6 | C5(q), F5(q), D5(q), B♭4(q) |
| 7 | F5(q), Rq, E♭5(e), D5(e), C5(q) |
| 8 | F5(q), Rq, E♭5(e), D5(e), C5(q) |
| 9 | D5(e), E♭5(e), F5(q), E♭5(q), D5(q) |
| 10 | C5(q), F5(q), B♭4(h) |
| 11 | A4(e), B♭4(e), C5(q), A4(e), B♭4(e), C5(q) |
| 12 | F5(q), C5(q), C5(h) |
| 13 | F5(q), C5(q), F5(q), C5(q) |
| 14 | B♭4(e), A4(e), G4(q), G4(q), C5(q) |
| 15 | A4(e), B♭4(e), C5(q), A4(e), B♭4(e), C5(q) |
| 16 | F5(q), C5(q), C5(h) |
| 17 | F5(q), C5(q), F5(q), C5(q) |
| 18 | A4(e), B♭4(e), C5(q), B♭4(q), Rq |

## 纯音符顺序

`D5(q), F5(q), E♭5(e), D5(e), C5(q), F5(q), E♭5(e), D5(e), C5(q), D5(e), E♭5(e), F5(q), E♭5(q), D5(q), C5(q), F5(q), D5(q), B♭4(q), F5(q), E♭5(e), D5(e), C5(q), F5(q), E♭5(e), D5(e), C5(q), D5(e), E♭5(e), F5(q), E♭5(q), D5(q), C5(q), F5(q), B♭4(h), A4(e), B♭4(e), C5(q), A4(e), B♭4(e), C5(q), F5(q), C5(q), C5(h), F5(q), C5(q), F5(q), C5(q), B♭4(e), A4(e), G4(q), G4(q), C5(q), A4(e), B♭4(e), C5(q), A4(e), B♭4(e), C5(q), F5(q), C5(q), C5(h), F5(q), C5(q), F5(q), C5(q), A4(e), B♭4(e), C5(q), B♭4(q)`

## 琴键坐标

本挑战使用 `musette-ultimate-f4` profile。坐标以 1612×720 横屏画面为基准；白键取接近底部的中心触点，黑键取键帽中心触点。

| 音高 | x | y | 本曲使用 |
|---|---:|---:|:---:|
| F4 | 173 | 600 | 否 |
| G4 | 294 | 600 | 是 |
| A4 | 415 | 600 | 是 |
| B♭4 | 476 | 475 | 是 |
| B4 | 536 | 600 | 否 |
| C5 | 673 | 600 | 是 |
| D5 | 794 | 600 | 是 |
| E♭5 | 855 | 475 | 是 |
| E5 | 915 | 600 | 否 |
| F5 | 1052 | 600 | 是 |
| G5 | 1173 | 600 | 否 |
| A5 | 1294 | 600 | 否 |
| B♭5 | 1355 | 475 | 否 |
| B5 | 1415 | 600 | 否 |

## 曲尾审计与停止边界

- `last_valid_event_index=68`
- `last_valid_pitch=B♭4`
- 最后有效音符：beat 70 按下，持续 1 拍，在 beat 71 释放
- `stop_after_beat=71`；释放 B♭4 后进入最后一拍休止，关闭 `playback_gate`
- 原冻结计划仍含 79 个事件。索引 69、beat 71 的 C5 已在画面中触发“要停顿”；索引 69–78 共 10 个事件是多余输入，不能计入正式谱面。

这说明设备 ACK 仅表示按键送达手机，不表示多邻国判定有效。正式曲目以画面中的绿色/黄色命中、连击状态和错误提示为准；三颗星结算也不能替代曲尾输入审计。

## 取证文件

- [完整 H.264 原流](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-7-two-anchor/full-stream.h264)
- [封装后的完整 MP4](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-7-two-anchor/full-stream.mp4)
- [曲尾 54–66 秒拼图](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-7-two-anchor/tail-54-66-montage.png)
- [设备时序日志](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-7-two-anchor/performance/timing-log.json)
- [播放器参数与动作记录](../../outputs/duolingo-stage4-section14-musette/ultimate/pass-7-two-anchor/player.stdout.json)
- [原始 79 事件冻结计划](../../outputs/duolingo-stage4-section14-musette/ultimate/musette-frozen-plan.json)

## 记录说明

正式谱面依据冻结计划的前 69 个事件、逐帧曲尾复核和最后一拍休止共同重建。原冻结计划及其测试仍保留了 10 个曲尾多余事件，因此仅作为问题证据，不能再作为完整正确谱面的时间 oracle；本文件的 18 小节、69 音版本是当前复核后的曲目记录。
