import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import sharp from "sharp";

const DEFAULT_THRESHOLD = 12;

function usage() {
  return [
    "Usage:",
    "  npm run visual:diff -- <reference.png> <implementation.png> [options]",
    "",
    "Options:",
    "  --output-dir <path>              Output directory (default: work/visual-diff)",
    "  --threshold <0-255>              Mean per-channel pixel tolerance (default: 12)",
    "  --min-within-tolerance <0-100>   Fail when the match percentage is lower",
    "  --max-mae <0-255>                Fail when mean absolute channel error is higher",
    "  --help                           Show this message",
    "",
    "The two images must have identical dimensions. This is intentional: capture the",
    "browser at the same viewport as the reference before comparing them.",
  ].join("\n");
}

function numberOption(name, raw, minimum, maximum) {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be between ${minimum} and ${maximum}; received ${raw}`);
  }
  return value;
}

function parseArguments(argv) {
  const positionals = [];
  const options = {
    outputDir: "work/visual-diff",
    threshold: DEFAULT_THRESHOLD,
    minWithinTolerance: null,
    maxMae: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--help" || argument === "-h") {
      console.log(usage());
      process.exit(0);
    }
    if (!argument.startsWith("--")) {
      positionals.push(argument);
      continue;
    }

    const rawValue = argv[index + 1];
    if (!rawValue || rawValue.startsWith("--")) {
      throw new Error(`${argument} requires a value`);
    }
    index += 1;

    if (argument === "--output-dir") options.outputDir = rawValue;
    else if (argument === "--threshold") options.threshold = numberOption(argument, rawValue, 0, 255);
    else if (argument === "--min-within-tolerance") options.minWithinTolerance = numberOption(argument, rawValue, 0, 100);
    else if (argument === "--max-mae") options.maxMae = numberOption(argument, rawValue, 0, 255);
    else throw new Error(`Unknown option: ${argument}`);
  }

  if (positionals.length < 2 || positionals.length > 3) {
    throw new Error(usage());
  }
  if (positionals[2]) options.outputDir = positionals[2];

  return {
    referencePath: positionals[0],
    implementationPath: positionals[1],
    ...options,
  };
}

const {
  referencePath,
  implementationPath,
  outputDir,
  threshold,
  minWithinTolerance,
  maxMae,
} = parseArguments(process.argv.slice(2));

const reference = sharp(referencePath).ensureAlpha();
const implementation = sharp(implementationPath).ensureAlpha();
const [referenceMeta, implementationMeta] = await Promise.all([
  reference.metadata(),
  implementation.metadata(),
]);

if (referenceMeta.width !== implementationMeta.width || referenceMeta.height !== implementationMeta.height) {
  throw new Error(
    `Image dimensions differ: reference=${referenceMeta.width}x${referenceMeta.height}, `
    + `implementation=${implementationMeta.width}x${implementationMeta.height}`,
  );
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
const halfOpacityImplementation = Buffer.from(implementationRaw);

for (let offset = 0; offset < referenceRaw.length; offset += 4) {
  const dr = Math.abs(referenceRaw[offset] - implementationRaw[offset]);
  const dg = Math.abs(referenceRaw[offset + 1] - implementationRaw[offset + 1]);
  const db = Math.abs(referenceRaw[offset + 2] - implementationRaw[offset + 2]);
  const da = Math.abs(referenceRaw[offset + 3] - implementationRaw[offset + 3]);
  const pixelMax = Math.max(dr, dg, db, da);
  const pixelMean = (dr + dg + db + da) / 4;

  if (pixelMax > 0) differingPixels += 1;
  if (pixelMean > threshold) perceptuallyDifferentPixels += 1;
  absoluteError += dr + dg + db + da;
  squaredError += dr * dr + dg * dg + db * db + da * da;
  maxChannelError = Math.max(maxChannelError, pixelMax);

  const intensity = Math.min(255, Math.round(pixelMean * 4));
  heatmap[offset] = intensity;
  heatmap[offset + 1] = pixelMean > 28 ? 24 : 0;
  heatmap[offset + 2] = pixelMean > 72 ? 180 : 0;
  heatmap[offset + 3] = pixelMax === 0 ? 0 : 230;
  halfOpacityImplementation[offset + 3] = Math.round(implementationRaw[offset + 3] * 0.5);
}

const pixelCount = width * height;
const channelCount = pixelCount * 4;
const withinTolerancePercent = Number(
  (((pixelCount - perceptuallyDifferentPixels) / pixelCount) * 100).toFixed(4),
);
const meanAbsoluteChannelError = Number((absoluteError / channelCount).toFixed(4));
const checks = {
  minWithinTolerance: minWithinTolerance === null
    ? null
    : { expected: minWithinTolerance, actual: withinTolerancePercent, passed: withinTolerancePercent >= minWithinTolerance },
  maxMae: maxMae === null
    ? null
    : { expected: maxMae, actual: meanAbsoluteChannelError, passed: meanAbsoluteChannelError <= maxMae },
};
const passed = Object.values(checks).every((check) => check === null || check.passed);
const metrics = {
  schemaVersion: 1,
  result: passed ? "passed" : "failed",
  reference: path.resolve(referencePath),
  implementation: path.resolve(implementationPath),
  viewport: { width, height },
  threshold,
  exactMatchPercent: Number((((pixelCount - differingPixels) / pixelCount) * 100).toFixed(4)),
  withinTolerancePercent,
  differingPixels,
  perceptuallyDifferentPixels,
  meanAbsoluteChannelError,
  rootMeanSquareChannelError: Number(Math.sqrt(squaredError / channelCount).toFixed(4)),
  maxChannelError,
  checks,
};

await mkdir(outputDir, { recursive: true });

await Promise.all([
  sharp(heatmap, { raw: { width, height, channels: 4 } })
    .png({ compressionLevel: 9 })
    .toFile(path.join(outputDir, "heatmap.png")),
  sharp(referenceRaw, { raw: { width, height, channels: 4 } })
    .composite([{ input: implementationRaw, raw: { width, height, channels: 4 }, blend: "difference" }])
    .png({ compressionLevel: 9 })
    .toFile(path.join(outputDir, "difference.png")),
  sharp(referenceRaw, { raw: { width, height, channels: 4 } })
    .composite([{ input: halfOpacityImplementation, raw: { width, height, channels: 4 }, blend: "over" }])
    .png({ compressionLevel: 9 })
    .toFile(path.join(outputDir, "overlay.png")),
  sharp({ create: { width: width * 2, height, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 1 } } })
    .composite([
      { input: referenceRaw, raw: { width, height, channels: 4 }, left: 0, top: 0 },
      { input: implementationRaw, raw: { width, height, channels: 4 }, left: width, top: 0 },
    ])
    .png({ compressionLevel: 9 })
    .toFile(path.join(outputDir, "comparison.png")),
  writeFile(path.join(outputDir, "metrics.json"), `${JSON.stringify(metrics, null, 2)}\n`, "utf8"),
]);

console.log(JSON.stringify(metrics, null, 2));
if (!passed) process.exitCode = 2;
