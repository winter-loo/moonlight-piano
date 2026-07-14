# 月光琴房 Web MVP

面向钢琴零基础用户、优先适配 iPad 横屏的互动练习产品。当前实现覆盖产品实现规划的阶段 0 和阶段 1：工程基线、统一音乐时钟、课程内容模型，以及《梦中的婚礼》第 6–7 小节的听辨与纯节奏关卡。

## 已实现

- 首页入口：`/`
- B1-01 听辨关卡：`/practice/B1-01`
- B1-02 纯节奏关卡：`/practice/B1-02`
- 引擎诊断台：`/lab/engine`
- `AudioContext` 主时钟、倒数、暂停、恢复和重来
- SVG 色块从右向左移动，固定判定线
- iPad 触控和电脑任意字符键节奏输入
- 命中、早晚、多按与漏按评分，80% 达标
- 第 6–7 小节结构化课程内容和运行时校验
- 帧率、最大帧间隔与输入分发延迟诊断

## 本地运行

要求 Node.js `>=22.13.0`。

```bash
npm install
npm run dev
```

开发服务器启动后打开终端显示的本地地址。首次播放或练习必须由用户点击触发，这是 iPad Safari 和 Chrome 的 Web Audio 限制。

## 质量检查

```bash
npm run lint
npm test
npm run build
```

`npm run test:all` 会连续执行音乐引擎单元测试和生产构建。iPad 视口与真机检查项见 [`tests/ipad-viewport-matrix.md`](tests/ipad-viewport-matrix.md)。

## 关键目录

- `app/practice/`：沉浸式练习路由
- `components/practice/`：阶段 1 关卡 UI
- `lib/music/`：课程 schema、音高和速度工具
- `lib/engine/`：Transport 与节奏评分
- `lib/audio/`：节拍器和临时合成音色
- `app/lab/engine/`：开发诊断台

阶段 2 将加入 G2–D5 自适应琴键、钢琴采样、统一触控/键盘输入，以及 B1-03、B1-04 右手练习。
