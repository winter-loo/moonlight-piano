# 月光琴房 Web MVP

面向钢琴零基础用户、优先适配 iPad 横屏的互动练习产品。当前版本用“看老师在虚拟钢琴上示范—用户重复弹奏—进入五线谱节奏跟弹”的短闭环，验证用户能否轻松、持续地学习《梦中的婚礼》第一段旋律。

## 当前能力

- 学习首页：`/`
- B1-01 听辨跟弹：`/practice/B1-01`
  - 虚拟钢琴自动示范旋律
  - 用户在同一架钢琴上重复弹奏
  - 错音反馈、连续错误后的琴键提示和完成反馈
- B1-02 五线谱节奏跟弹：`/practice/B1-02`
  - 色块在五线谱上从右向左移动
  - 固定判定线、三拍倒数、暂停、继续和重来
  - 触控钢琴与电脑键盘输入
  - 命中、早晚、多按与漏按评分，80% 达标
- 音乐引擎诊断页：`/lab/engine`
- 首页自由钢琴：左右手独立快捷键、跨八度输入和 Web Audio 合成音色

## 技术基线

- Next.js 16、React 19、TypeScript
- Vinext/Vite 与 Cloudflare 适配
- Web Audio API 作为练习时钟与临时音色引擎
- Bravura 开源音乐字体用于谱号与音乐符号
- 结构化课程内容、节奏评分与 Transport 独立于界面组件

运行要求：Node.js `>=22.13.0`。

```bash
npm install
npm run dev
```

浏览器首次播放声音必须由用户点击触发，这是 iPad Safari 和 Chrome 的 Web Audio 安全限制。

## 质量检查

```bash
npm run lint
npm test
npm run build
```

`npm run test:all` 会依次运行音乐引擎单元测试和生产构建。iPad 设备与视口检查见 [`docs/qa/iPad-视口验收矩阵.md`](docs/qa/iPad-视口验收矩阵.md)。

视觉回归工具用于比较同尺寸的设计参考图与浏览器截图：

```bash
npm run visual:diff -- reference.png implementation.png \
  --output-dir work/visual-diff \
  --min-within-tolerance 97 \
  --max-mae 4
```

工具会生成指标报告、并排图、叠加图、差异图和热力图；详细说明见 [`docs/qa/视觉回归工具.md`](docs/qa/视觉回归工具.md)。

## 仓库结构

```text
app/                    页面、路由和自由钢琴
components/practice/    练习五线谱、虚拟钢琴和关卡 UI
lib/audio/              音频调度
lib/engine/             Transport 与节奏评分
lib/music/              课程 schema、音高、速度和内容
docs/product/           产品文档与实现规划
docs/curriculum/        课程、关卡和曲目校准文档
docs/qa/                视觉验收、设备矩阵和证据
scripts/                开发与视觉回归工具
tests/unit/             音乐引擎单元测试
```

完整文档导航见 [`docs/README.md`](docs/README.md)。

## 当前边界

- 当前是核心可行性验证，不是完整课程或正式发行版本。
- 课程只校准了首个练习片段；后续仍需校准左右手、指法、合手与完整演奏内容。
- 临时音色由 Web Audio 合成，尚未接入正式钢琴采样和 MIDI 设备。
- 《梦中的婚礼》的参考谱、视频和课程转录资料仅用于验证与研究；公开发布课程内容前必须完成版权与授权审查。

## 文档语言

产品与课程文档以中文为主；代码标识、命令和技术接口保留英文。
