"""Supplement the compiler/link boundary with a fail-closed source policy.

Not a general Rust parser or proof: the no_std object and render tests are the
primary checks. New realtime source files/imports require explicit review here.
"""
import pathlib
import hashlib
import re

root = pathlib.Path(__file__).resolve().parents[1]
source = root / 'crates/moonlight-dsp/src'
expected = {'lib.rs', 'realtime.rs', 'basic.rs'}
actual = {str(p.relative_to(source)) for p in source.rglob('*.rs')}
if actual != expected:
    raise SystemExit('Realtime source set changed: update audited closure deliberately')
# The thin public wrapper is part of the contract too. A change requires a
# fresh explicit audit, not merely scanning the inner numeric loop.
# Issue #7 audit: physical parameter validation/pole compilation stays in new;
# process/reset/diagnostics/state_counts use only bounded numeric state, static
# error mapping and borrowed buffers. Independent no_std/object + allocation
# tests cover the changed production closure; this digest records that review.
expected_wrapper_sha256 = '120fe9db15d9291a2a2ecf4d08e74c364639a0e1efe2788435a94bb2e5bc4039'
if hashlib.sha256((source/'lib.rs').read_bytes()).hexdigest() != expected_wrapper_sha256:
    raise SystemExit('Public render wrapper changed: re-audit call closure and allocation/error paths')
for filename in ('realtime.rs', 'basic.rs'):
    text = (source / filename).read_text()
    text = re.sub(r'//[^\n]*', '', text)
    for forbidden in [r'\b(?:std|alloc)\s*::', r'\bunsafe\b', r'\bextern\b',
                      r'\b(?:include|include_str|include_bytes|panic|assert|assert_eq|todo|unimplemented)\s*!',
                      r'\b(?:unwrap|expect)\s*\(', r'\bloop\s*\{',
                      r'\b(?:Mutex|RwLock|Vec|Box|String|VecDeque)\b',
                      r'\b(?:print|println|eprint|eprintln|dbg)\s*!']:
        if re.search(forbidden, text):
            raise SystemExit(f'Forbidden realtime construct in {filename}: {forbidden}')
print('Production realtime source policy checked; C4 compiled-object audit is separate')
