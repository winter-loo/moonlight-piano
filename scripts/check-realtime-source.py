"""Supplement the compiler/link boundary with a fail-closed source policy.

Not a general Rust parser or proof: the no_std object and render tests are the
primary checks. New realtime source files/imports require explicit review here.
"""
import pathlib
import hashlib
import re

root = pathlib.Path(__file__).resolve().parents[1]
source = root / 'crates/moonlight-dsp/src'
expected = {'lib.rs', 'realtime.rs'}
actual = {str(p.relative_to(source)) for p in source.rglob('*.rs')}
if actual != expected:
    raise SystemExit('Realtime source set changed: update audited closure deliberately')
# The thin public wrapper is part of the contract too. A change requires a
# fresh explicit audit, not merely scanning the inner numeric loop.
expected_wrapper_sha256 = '8f3f8eff50ead1ad745f5701859af116d7393b820860218143145d46478cea22'
if hashlib.sha256((source/'lib.rs').read_bytes()).hexdigest() != expected_wrapper_sha256:
    raise SystemExit('Public render wrapper changed: re-audit call closure and allocation/error paths')
text = (source / 'realtime.rs').read_text()
text = re.sub(r'//[^\n]*', '', text)
for forbidden in [r'\b(?:std|alloc)\s*::', r'\bunsafe\b', r'\bextern\b',
                  r'\b(?:include|include_str|include_bytes|panic|assert|assert_eq|todo|unimplemented)\s*!',
                  r'\b(?:unwrap|expect)\s*\(', r'\bloop\s*\{',
                  r'\b(?:Mutex|RwLock|Vec|Box|String|VecDeque)\b',
                  r'\b(?:print|println|eprint|eprintln|dbg)\s*!']:
    if re.search(forbidden, text):
        raise SystemExit(f'Forbidden realtime construct: {forbidden}')
print('Production realtime source policy checked; compile/link audit is separate')
