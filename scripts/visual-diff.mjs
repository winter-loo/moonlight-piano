import sharp from "sharp";
import path from "node:path";
import { mkdir } from "node:fs/promises";

const [referencePath, implementationPath, outputDir = "work/visual-diff"] = process.argv.slice(2);

if (!referencePath || !implementationPath) {
  throw new Error("Usage: node scripts/visual-diff.mjs <reference.png> <implementation.png> [output-dir]");
}

const reference = sharp(referencePath).ensureAlpha();
const implementation = sharp(implementationPath).ensureAlpha();
const [referenceMeta, implementationMeta] = await Promise.all([reference.metadata(), implementation.metadata()]);

if (referenceMeta.width !== implementationMeta.width || referenceMeta.height !== implementationMeta.height) {
  throw new Error(`Image dimensions differ: reference=${referenceMeta.width}x${referenceMeta.height}, implementation=${implementationMeta.width}x${implementationMeta.height}`);
}

const width = referenceMeta.width;
const height = referenceMeta.height;
const [referenceRaw, implementationRaw] = await Promise.all([
  reference.raw().toBuffer(),
  implementation.raw().toBuffer(),
]);

let differingPixels = 0;
let perceptuallyDifferentPixels = 0;
let absoluteError = 0;
let squaredError = 0;
let maxChannelError = 0;
const heatmap = Buffer.alloc(referenceRaw.length);

for (let offset = 0; offset < referenceRaw.length; offset += 4) {
  const dr = Math.abs(referenceRaw[offset] - implementationRaw[offset]);
  const dg = Math.abs(referenceRaw[offset + 1] - implementationRaw[offset + 1]);
  const db = Math.abs(referenceRaw[offset + 2] - implementationRaw[offset + 2]);
  const da = Math.abs(referenceRaw[offset + 3] - implementationRaw[offset + 3]);
  const pixelMax = Math.max(dr, dg, db, da);
  const pixelMean = (dr + dg + db + da) / 4;

  if (pixelMax > 0) differingPixels += 1;
  if (pixelMean > 12) perceptuallyDifferentPixels += 1;
  absoluteError += dr + dg + db + da;
  squaredError += dr * dr + dg * dg + db * db + da * da;
  maxChannelError = Math.max(maxChannelError, pixelMax);

  const intensity = Math.min(255, Math.round(pixelMean * 4));
  heatmap[offset] = intensity;
  heatmap[offset + 1] = pixelMean > 28 ? 24 : 0;
  heatmap[offset + 2] = pixelMean > 72 ? 180 : 0;
  heatmap[offset + 3] = pixelMax === 0 ? 0 : 230;
}

const pixelCount = width * height;
const channelCount = pixelCount * 4;
const metrics = {
  reference: path.resolve(referencePath),
  implementation: path.resolve(implementationPath),
  viewport: `${width}x${height}`,
  exactMatchPercent: Number((((pixelCount - differingPixels) / pixelCount) * 100).toFixed(4)),
  withinTolerancePercent: Number((((pixelCount - perceptuallyDifferentPixels) / pixelCount) * 100).toFixed(4)),
  differingPixels,
  perceptuallyDifferentPixels,
  meanAbsoluteChannelError: Number((absoluteError / channelCount).toFixed(4)),
  rootMeanSquareChannelError: Number(Math.sqrt(squaredError / channelCount).toFixed(4)),
  maxChannelError,
};

await mkdir(outputDir, { recursive: true });

await sharp(heatmap, { raw: { width, height, channels: 4 } })
  .png({ compressionLevel: 9 })
  .toFile(path.join(outputDir, "heatmap.png"));

await sharp(referenceRaw, { raw: { width, height, channels: 4 } })
  .composite([{ input: implementationRaw, raw: { width, height, channels: 4 }, blend: "difference" }])
  .png({ compressionLevel: 9 })
  .toFile(path.join(outputDir, "overlay.png"));

await sharp({ create: { width: width * 2, height, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 1 } } })
  .composite([
    { input: referenceRaw, raw: { width, height, channels: 4 }, left: 0, top: 0 },
    { input: implementationRaw, raw: { width, height, channels: 4 }, left: width, top: 0 },
  ])
  .png({ compressionLevel: 9 })
  .toFile(path.join(outputDir, "comparison.png"));

console.log(JSON.stringify(metrics, null, 2));
