# Visual QA — B1-02 五线谱节奏跟弹

- **Source visual truth:** `C:\Users\HSPCAD~1\AppData\Local\Temp\codex-clipboard-40819788-a208-4db2-b0f2-9189206adfb1.png`
- **Implementation screenshot:** `tmp/qa/b1-02-ready.png`
- **Viewport:** 1280 × 720（内置浏览器，横屏）
- **State:** B1-02 初始状态；五线谱、移动色块起点、判定线与虚拟钢琴同时可见
- **Full-view comparison evidence:** `tmp/qa/b1-02-full-comparison.png`
- **Focused comparison evidence:** `tmp/qa/b1-02-focused-comparison.png`
- **Running-state evidence:** `tmp/qa/b1-02-running.png`

## Findings

- No actionable P0, P1, or P2 fidelity issues remain.
- [P3] 实现保留“月光琴房”的深蓝品牌外壳，而参考图使用纯白全屏；核心练习区采用参考图的浅色五线谱与白色钢琴，结构与对比关系一致。
- [P3] 参考图展示示例 A/D/E/F/G 片段；实现使用课程真实目标 `D–G–B♭–D–C`，避免为了截图一致而展示错误课程内容。
- [P3] 实现把十个白键放在连续琴床上，仅以分组边框区分 C/D/E、F/G/A/B、C/D/E；参考图的三组间距更大。当前分组仍清晰，且连续琴床更接近真实钢琴。

## Required Fidelity Surfaces

- **Fonts and typography:** Bravura 开源音乐字体负责高音谱号与降号；课程标题沿用既有中式衬线层级，音名使用圆体粗字。
- **Spacing and layout rhythm:** 练习区按“进度/说明 → 五线谱 → 钢琴 → 操作”排列；1280 × 720 下所有主要操作均在首屏，无滚动和裁切。
- **Colors and visual tokens:** 五线谱使用浅灰线、白色谱面和青色判定线；节奏块按音名着色；钢琴保持高对比黑白键。
- **Image and notation quality:** 高音谱号与降号来自 Bravura OTF，不使用截图裁片或占位符；动态谱面和色块由实时课程数据渲染。
- **Copy and content:** 明确说明“任意琴键都算一次落点，本关只评分节奏”，避免用户误以为这一关会因音高出错而失败。

## Interaction Verification

- “开始练习”进入三拍倒数；倒数结束后钢琴解锁。
- 色块随统一练习时钟从右向左移动并经过固定判定线。
- 触摸/鼠标点击十个白键或七个黑键会播放对应音高，并提交一次节奏落点。
- 电脑键盘 A–P 快捷键仍映射到虚拟琴键；空格和回车可作为无音高要求的节奏输入。
- 暂停、继续、重来以及 12 拍结束后的结果态均可用。
- 浏览器验证了初始、倒数、运行、琴键解锁、输入反馈与自动结束状态。
- 最终页面控制台检查：无页面错误或警告。

## Comparison History

- Pass 1: 参考与实现的核心结构一致，但 Bravura 高音谱号尾部贴近谱面底边，记为 P2。
- Pass 2: 上移并缩小高音谱号，保持参考图的视觉重量，同时完整落在谱面内；P2 已解决。完整与局部对照均未发现新的 P0/P1/P2。

final result: passed
