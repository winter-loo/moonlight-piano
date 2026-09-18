import { LegacyWebAudioEngine, type LegacyWebAudioProfile } from "./legacy-web-audio-engine.ts";
import type { SoundEngine } from "./sound-engine.ts";

export const BROWSER_SOUND_ENGINES = [
  {
    id: "legacy-lesson-tone",
    label: "当前课程音色",
    description: "保留课程示范使用的三角波与二次泛音声音。",
    profile: "lesson-tone",
  },
  {
    id: "legacy-interactive-piano",
    label: "当前交互钢琴",
    description: "保留首页可演奏键盘的三泛音、滤波与压缩声音。",
    profile: "interactive-piano",
  },
] as const satisfies readonly {
  id: string;
  label: string;
  description: string;
  profile: LegacyWebAudioProfile;
}[];

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
  return new LegacyWebAudioEngine({
    id: descriptor.id,
    label: descriptor.label,
    profile: descriptor.profile,
    context: options.context,
    ownsContext: options.ownsContext,
  });
}

/**
 * Compatibility seam for existing score schedulers that already own an
 * AudioContext. Sound generation still goes through the same SoundEngine
 * contract; the adapter never closes the caller-owned context.
 */
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
