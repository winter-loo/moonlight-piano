# 月光琴房文档导航

文档按“产品为什么做、课程教什么、实现怎么做、质量如何验证”组织。版本号保留在文件名中，方便核心验证期记录重大决策变化。

## 产品

- [`product/月光琴房-产品文档-v0.1.md`](product/月光琴房-产品文档-v0.1.md)：产品定位、用户、教学模型、交互与 MVP 范围
- [`product/月光琴房-产品实现规划-v0.1.md`](product/月光琴房-产品实现规划-v0.1.md)：技术原则、数据模型、练习引擎、阶段与验收标准
- [`product/月光琴房-专业物理建模钢琴音色规范-v0.1.md`](product/月光琴房-专业物理建模钢琴音色规范-v0.1.md)：Pianoteq 级专业物理建模钢琴的产品目标、Rust/WASM 架构、声学模型、实时性能与验收规范

## 课程与内容

- [`curriculum/月光琴房-课程与关卡设计文档-v0.1.md`](curriculum/月光琴房-课程与关卡设计文档-v0.1.md)：课程目标、能力地图、章节和标准练习循环
- [`curriculum/梦中的婚礼-课程拆解表-v0.1.md`](curriculum/梦中的婚礼-课程拆解表-v0.1.md)：章节与关卡拆解
- [`curriculum/梦中的婚礼-内容校准表-v0.1.md`](curriculum/梦中的婚礼-内容校准表-v0.1.md)：首个片段的音乐事实、事件与待实测项

## 实机练习曲目

- [`practiced-songs/bicycle-built-for-two.md`](practiced-songs/bicycle-built-for-two.md)：Bicycle Built for Two
- [`practiced-songs/greensleeves.md`](practiced-songs/greensleeves.md)：Greensleeves
- [`practiced-songs/when-the-saints-go-marching-in.md`](practiced-songs/when-the-saints-go-marching-in.md)：When The Saints Go Marching In
- [`practiced-songs/little-miss-cant-be-wrong.md`](practiced-songs/little-miss-cant-be-wrong.md)：Little Miss Can’t Be Wrong

## 质量与验证

- [`qa/视觉回归工具.md`](qa/视觉回归工具.md)：像素比较命令、指标、产物与自动判定
- [`qa/B1-02-视觉验收.md`](qa/B1-02-视觉验收.md)：五线谱节奏关卡的参考图、验收记录和证据
- [`qa/iPad-视口验收矩阵.md`](qa/iPad-视口验收矩阵.md)：目标设备、视口与发布前手工检查

## 维护约定

- 产品方向变化先更新产品文档，再更新实现规划和课程文档。
- 音乐事实变化必须同步更新内容校准表与 `lib/music/content/`。
- 已完成的实机曲谱、时值和成绩证据统一维护在 `practiced-songs/`，一首曲子一个文件。
- QA 临时产物输出到 `work/`；只有能解释具体结论的精选证据进入 `docs/qa/evidence/`。
- 文档不得引用个人电脑绝对路径；外部资料使用可访问的公开链接并标明用途。
