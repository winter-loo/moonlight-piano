import sharp from "sharp";
import path from "node:path";
import { mkdir } from "node:fs/promises";

const source = process.argv[2];
const output = process.argv[3] ?? "public/assets";

if (!source) {
  throw new Error("Usage: node scripts/extract-reference-assets.mjs <reference.png> [output-dir]");
}

const crops = [
  ["reference-hero-piano.png", 720, 0, 518, 238],
  ["reference-sidebar-still-life.png", 0, 540, 234, 275],
  ["reference-learning-map.png", 257, 312, 400, 430],
  ["reference-practice-score.png", 688, 314, 517, 248],
  ["reference-keyboard.png", 677, 597, 533, 149],
  ["reference-stability-chart.png", 1260, 559, 263, 183],
  ["reference-encouragement.png", 1238, 773, 306, 107],
  ["reference-bottom-wave-left.png", 235, 890, 305, 113],
  ["reference-bottom-wave-right.png", 985, 890, 583, 113],
  ["reference-start-button.png", 540, 878, 445, 84],
  ["reference-brand.png", 28, 35, 185, 106],
  ["reference-hero-copy.png", 329, 74, 405, 121],
  ["reference-goals-card.png", 1238, 59, 306, 275],
  ["reference-streak-card.png", 1238, 345, 306, 149],
  ["reference-stability-card.png", 1238, 507, 306, 253],
  ["reference-course-header.png", 256, 238, 402, 76],
  ["reference-practice-header.png", 673, 238, 549, 76],
  ["reference-practice-footer.png", 673, 760, 549, 80],
  ["reference-selected-nav.png", 18, 180, 205, 61],
];

await mkdir(output, { recursive: true });

for (const [name, left, top, width, height] of crops) {
  await sharp(source)
    .extract({ left, top, width, height })
    .png({ compressionLevel: 9 })
    .toFile(path.join(output, name));
}

console.log(JSON.stringify({ source, output, crops: crops.map(([name, left, top, width, height]) => ({ name, left, top, width, height })) }, null, 2));
