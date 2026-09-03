# When The Saints Go Marching In – 莎丽版本

## 基本信息

- 应用：Duolingo Music
- 设备：OPPO PHJ110
- 课程位置：第 4 阶段、第 12 部分
- 谱号：高音谱号
- 拍号：4/4
- 调号：B♭、E♭ 两个降号；音集与 B♭ 大调/G 小调相容
- 临时升降号：未见调号以外的临时升降号
- 音域：B♭4–F5
- 完成结果：1000 分、三颗星；音高 100%、节奏 99%、20 经验

课程标题证据：[标题卡](../../outputs/duolingo-stage4-section12/first-pass-title-card.png)；最终三星证据：[1000 分结算页](../../outputs/duolingo-stage4-section12/pass-11-repeated-middle/result.png)；完整事件账本：[第 10 遍完整动作](../../outputs/duolingo-stage4-section12/pass-10-complete-score/full-actions.json)。

## 时值与演奏参数

- 19 个 4/4 小节，共 72 个音符。
- 四分音符 27、八分音符 40、二分音符 5；音符合计 57 拍，休止符合计 19 拍。
- 音高计数：B♭4×16、C5×7、D5×24、E♭5×10、F5×15。
- 正式事件账本采用 80 BPM，四分音符 750 ms；相邻音提前 20 ms 释放，因此四分实际约 730 ms、八分约 355 ms、二分约 1480 ms。

记号：`e`=八分音符，`q`=四分音符，`h`=二分音符，`Re`=八分休止，`Rq`=四分休止，`Rh`=二分休止。

## 完整谱面

| 小节 | 事件 |
|---:|---|
| 1 | C5(q), Rq, Rh |
| 2 | Rh, Re, B♭4(e), D5(e), E♭5(e) |
| 3 | F5(q), Rq, Re, B♭4(e), D5(e), E♭5(e) |
| 4 | F5(q), Rq, Re, B♭4(e), D5(e), E♭5(e) |
| 5 | F5(q), D5(q), B♭4(q), D5(q) |
| 6 | C5(h), Re, D5(e), D5(e), C5(e) |
| 7 | B♭4(q), Re, B♭4(e), D5(e), Re, F5(e), F5(e) |
| 8 | F5(e), E♭5(e), Rq, Rq, D5(e), E♭5(e) |
| 9 | F5(q), D5(q), B♭4(q), D5(q) |
| 10 | B♭4(h), Re, B♭4(e), D5(e), E♭5(e) |
| 11 | F5(q), Rq, Re, B♭4(e), D5(e), E♭5(e) |
| 12 | F5(q), Rq, Re, B♭4(e), D5(e), E♭5(e) |
| 13 | F5(q), D5(q), B♭4(q), D5(q) |
| 14 | C5(h), F5(q), D5(q) |
| 15 | B♭4(q), D5(q), C5(h) |
| 16 | Re, D5(e), D5(e), C5(e), B♭4(q), Re, B♭4(e) |
| 17 | D5(e), Re, F5(e), F5(e), F5(e), E♭5(e), Rq |
| 18 | Rq, D5(e), E♭5(e), F5(q), D5(q) |
| 19 | B♭4(q), D5(q), C5(h) |

## 纯音符顺序

`C5(q), B♭4(e), D5(e), E♭5(e), F5(q), B♭4(e), D5(e), E♭5(e), F5(q), B♭4(e), D5(e), E♭5(e), F5(q), D5(q), B♭4(q), D5(q), C5(h), D5(e), D5(e), C5(e), B♭4(q), B♭4(e), D5(e), F5(e), F5(e), F5(e), E♭5(e), D5(e), E♭5(e), F5(q), D5(q), B♭4(q), D5(q), B♭4(h), B♭4(e), D5(e), E♭5(e), F5(q), B♭4(e), D5(e), E♭5(e), F5(q), B♭4(e), D5(e), E♭5(e), F5(q), D5(q), B♭4(q), D5(q), C5(h), F5(q), D5(q), B♭4(q), D5(q), C5(h), D5(e), D5(e), C5(e), B♭4(q), B♭4(e), D5(e), F5(e), F5(e), F5(e), E♭5(e), D5(e), E♭5(e), F5(q), D5(q), B♭4(q), D5(q), C5(h)`

## 记录说明

这首曲目的困难不在音高集合，而在大量八分休止、连续八分音符和重复段落。最终账本使用绝对时钟发送 144 个 DOWN/UP 事件，并以设备 ACK 验证输入到达。
