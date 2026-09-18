import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const ROOT = path.resolve(import.meta.dirname, "../..");

test("acoustic workflows never rewrite or push the checked-out source", async () => {
  for (const name of ["acoustic-analysis", "acoustic-data-registry"]) {
    const text = await readFile(path.join(ROOT, `.github/workflows/${name}.yml`), "utf8");
    assert.match(text, /contents: read/);
    assert.match(text, /persist-credentials: false/);
    assert.match(text, /git diff --exit-code/);
    assert.doesNotMatch(text, /contents: write|git push|git commit|git add -A|apply-acoustic-round2|acoustic-round2\.part/);
    assert.ok(text.includes(`${name === "acoustic-analysis" ? "acoustic-analysis" : "acoustic-provenance"}-\${{ github.sha }}`));
    assert.doesNotMatch(text, /github\.event\.pull_request\.head\.sha/);
  }
  const names = await readdir(path.join(ROOT, ".github/scripts")).catch((error) => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  assert.ok(names.every((name) => !name.startsWith("acoustic-round2.") && name !== "apply-acoustic-round2.py"));
});

test("workflows retain integrity, application and acoustic estimator gates", async () => {
  const registry = await readFile(path.join(ROOT, ".github/workflows/acoustic-data-registry.yml"), "utf8");
  const analysis = await readFile(path.join(ROOT, ".github/workflows/acoustic-analysis.yml"), "utf8");
  for (const command of ["npm test", "npm run lint", "npm run build", "npm run acoustic:validate", "npm run acoustic:ingest:all", "npm run acoustic:report"]) {
    assert.ok(registry.includes(command), command);
  }
  for (const command of ["unittest discover -s tests/acoustics", "tools.acoustics.fixtures", "--rendered-rate 96000", "scripts/prepare-acoustic-analysis.mjs --case salamander-c4-reference", "git ls-files -- work/acoustic-data/raw"]) {
    assert.ok(analysis.includes(command), command);
  }
  const { scripts } = JSON.parse(await readFile(path.join(ROOT, "package.json"), "utf8"));
  for (const text of [registry, analysis]) {
    for (const match of text.matchAll(/npm run ([\w:-]+)/g)) {
      assert.equal(typeof scripts[match[1]], "string", `undefined npm script: ${match[1]}`);
    }
  }
});
