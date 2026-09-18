#!/bin/sh
# Run from the repository root, on Linux CI or a developer toolchain.
set -eu
mkdir -p work/realtime
# Compile the actual production render closure, not a parallel test renderer.
printf '#![no_std]\n#[path="../../crates/moonlight-dsp/src/realtime.rs"] pub mod realtime;\n' > work/realtime/audit.rs
rustc --edition=2021 --crate-type lib --emit=obj -C opt-level=3 -C panic=abort \
  -C overflow-checks=no work/realtime/audit.rs -o work/realtime/audit.o
nm -g work/realtime/audit.o > work/realtime/defined-symbols.txt
nm -u work/realtime/audit.o > work/realtime/undefined-symbols.txt
# Both parts are required: real render code must survive compilation, and the
# object may depend only on reviewed bounded memory intrinsics (ELF or Mach-O).
python3 scripts/check-realtime-symbols.py \
  work/realtime/defined-symbols.txt work/realtime/undefined-symbols.txt
python3 scripts/check-realtime-source.py
