#!/usr/bin/env bash
set -euo pipefail

output_dir="${1:-work/physical-c4}"
sample_rate="${SAMPLE_RATE:-48000}"
block_size="${BLOCK_SIZE:-128}"
duration="${DURATION_SECONDS:-6}"
seed="${SEED:-1297043278}"

cargo run --quiet -p moonlight-offline --bin moonlight-render -- \
  --model fixtures/physical-c4/minimal-c4.mlpiano \
  --events fixtures/physical-c4/c4.events.csv \
  --sample-rate "$sample_rate" \
  --block-size "$block_size" \
  --duration "$duration" \
  --seed "$seed" \
  --output-dir "$output_dir"

printf 'WAV: %s/c4-reference.wav\n' "$output_dir"
printf 'Metrics: %s/c4-report.json\n' "$output_dir"
printf 'Energy: %s/c4-energy.csv\n' "$output_dir"
printf 'Timing: %s/c4-timing.json\n' "$output_dir"
