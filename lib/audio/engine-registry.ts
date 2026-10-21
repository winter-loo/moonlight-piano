import { LegacyWebAudioEngine, type LegacyWebAudioProfile } from "./legacy-web-audio-engine.ts";
import { PhysicalC4WorkletEngine } from "./physical-c4-worklet-engine.ts";
import type { SoundEngine } from "./sound-engine.ts";

export const BROWSER_SOUND_ENGINES = [
  {
    id: "basic-piano",
    label: "Rust 基础全键盘",
    description: "分析式参数的 88 键、最多 32 个同时发声的按键；音质和踏板仍在开发。",
    kind: "physical" as const,
    profile: "basic-piano",
    labLevel: 1.0,
  },
  {
    id: "physical-c4",
    label: "Rust 物理 C4",
    description: "非线性琴槌驱动持久 C4 琴弦，力度连续改变击弦与泛音；参数待实琴校准，制音器与踏板尚未实现。",
    kind: "physical" as const,
    profile: "physical-c4",
    labLevel: 1.0,
  },
  {
    id: "legacy-lesson-tone",
    label: "当前课程音色",
    description: "课程示范的三角波与二次泛音基线，用于响度匹配 A/B。",
    kind: "legacy" as const,
    profile: "lesson-tone" as LegacyWebAudioProfile,
    labLevel: 0.24,
  },
  {
    id: "legacy-interactive-piano",
    label: "当前交互钢琴",
    description: "首页三泛音、滤波与压缩基线，用于响度匹配 A/B。",
    kind: "legacy" as const,
    profile: "interactive-piano" as LegacyWebAudioProfile,
    labLevel: 0.24,
  },
] as const;

export type BrowserSoundEngineId = (typeof BROWSER_SOUND_ENGINES)[number]["id"];

export type BrowserSoundEngineOptions = {
  context?: AudioContext;
  ownsContext?: boolean;
};

const lessonEngineByContext = new WeakMap<AudioContext, SoundEngine>();

export function getBrowserSoundEngineDescriptor(id: BrowserSoundEngineId) {
  const descriptor = BROWSER_SOUND_ENGINES.find((candidate) => candidate.id === id);
  if (!descriptor) throw new Error(`Unknown browser sound engine: ${id}`);
  return descriptor;
}

export function createBrowserSoundEngine(
  id: BrowserSoundEngineId,
  options: BrowserSoundEngineOptions = {},
): SoundEngine {
  const descriptor = getBrowserSoundEngineDescriptor(id);
  if (descriptor.kind === "physical") {
    return new PhysicalC4WorkletEngine({ ...options, mode: id === "basic-piano" ? "basic" : "c4" });
  }
  return new LegacyWebAudioEngine({
    id: descriptor.id,
    label: descriptor.label,
    profile: descriptor.profile,
    context: options.context,
    ownsContext: options.ownsContext,
  });
}

export function getLegacyLessonEngineForContext(context: AudioContext) {
  const existing = lessonEngineByContext.get(context);
  if (existing) return existing;
  const engine = createBrowserSoundEngine("legacy-lesson-tone", {
    context,
    ownsContext: false,
  });
  lessonEngineByContext.set(context, engine);
  return engine;
}
