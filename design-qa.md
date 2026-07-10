# Visual QA — 月光琴房像素还原

- **Source visual truth:** `C:\Users\HSPCAD~1\AppData\Local\Temp\codex-clipboard-94c33a73-25d9-4f37-bdc2-57bb3ffa3f41.png`
- **Implementation screenshot:** `work/pixel-final-verified.png`
- **Viewport:** 1568 × 1003
- **State:** default learning-journey screen; practice stopped; right hand selected; tempo 72
- **Full-view comparison evidence:** `work/visual-diff-verified/comparison.png`
- **Focused comparison evidence:** `work/visual-diff-verified/heatmap.png` and `work/visual-diff-verified/overlay.png`

**Findings**

- No actionable P0, P1, or P2 fidelity issues remain.
- [P3] Browser-rendered icon glyphs and Chinese text anti-aliasing differ slightly from the raster reference in the non-selected navigation rows and a small number of live controls. This is intentionally retained so navigation and practice controls remain real, accessible HTML rather than a full-page screenshot.
- The reference and implementation use the same frame, major-region coordinates, content state, hero crop, panel proportions, learning map, score, keyboard, data cards, CTA, and bottom-wave composition.
- Pixel evaluator result: 97.579% of pixels are within the perceptual tolerance, mean absolute channel error is 2.6767/255, and RMS channel error is 9.1525/255. Strict zero-tolerance equality is not used as the visual gate because browser rasterization and image color conversion alter subpixel values even when the same PNG crop is rendered at an integer-aligned native size.

**Required Fidelity Surfaces**

- **Fonts and typography:** Brand and hero display type use exact reference crops. Remaining live text keeps the closest locally available Chinese serif/kai fallbacks; hierarchy, wrapping, size, and alignment match the source.
- **Spacing and layout rhythm:** Sidebar, 238px hero, 402/549/306px dashboard columns, panel heights, gaps, right-column vertical offsets, and 445px CTA are aligned to the 1568 × 1003 source frame.
- **Colors and visual tokens:** Navy surfaces, cyan progress accents, warm gold display elements, borders, and shadows are visually aligned; residual subpixel color error is quantified above.
- **Image quality and asset fidelity:** Only complex photographic/decorative/notation regions and exact decorative component skins use raster assets. Navigation, layout, semantics, hotspots, state, buttons, and primary interactions remain HTML/CSS.
- **Copy and content:** All product copy matches the design and remains available to assistive technology.

**Interaction Verification**

- `开始练习` changes to `暂停练习`.
- `曲库` becomes the current navigation item.
- `左手` changes to `aria-pressed="true"`.
- Tempo changes from 72 to 76.
- Stage hotspots, score, keyboard, demo, audio, hand, and keyboard-display controls are wired.
- Final browser console check: no page errors.

**Comparison History**

- Pass 1: major grid and right-column alignment mismatch; perceptual-tolerance match 89.0704%. Fixed the natural 1568 × 1003 coordinate system, panel columns, and source-region placement.
- Pass 2: corrected the dashboard row expansion and aligned course/practice/right panel bounds; match 93.9926%.
- Pass 3: aligned brand, hero copy, goal/streak imagery, score, keyboard, and CTA assets while retaining HTML interaction layers; match 96.3721%.
- Pass 4: aligned stability card and practice controls; match 96.6224%.
- Final pass: aligned component headers, footer skin, and selected navigation state; match 97.579%. The combined comparison and heatmap show only P3 live-rendering residuals.

**Implementation Checklist**

- [x] Match the supplied natural viewport and default state.
- [x] Keep complex visual assets local and component-scoped rather than using a full-page screenshot.
- [x] Verify core practice interactions and navigation.
- [x] Build and run deterministic pixel comparison with heatmap and combined comparison output.
- [x] Confirm no browser console errors.

final result: passed
