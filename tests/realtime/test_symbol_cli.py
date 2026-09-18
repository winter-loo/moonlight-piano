"""Known nm output tests the audit policy, not a substitute for compiling DSP."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts/check-realtime-symbols.py'
RENDER = '00000000 T _ZN5audit8realtime13RealtimeState13process_block17h123E\n'


class SymbolPolicy(unittest.TestCase):
    def run_check(self, defined=RENDER, undefined=''):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'defined').write_text(defined)
            (root / 'undefined').write_text(undefined)
            return subprocess.run(
                [sys.executable, str(CHECKER), str(root / 'defined'), str(root / 'undefined')],
                capture_output=True, text=True, timeout=5,
            )

    def test_renderer_with_no_external_symbols_is_valid(self):
        self.assertEqual(self.run_check().returncode, 0)

    def test_elf_and_macho_memory_intrinsics_are_allowed(self):
        for text in (' U memset\n U memcpy\n U memmove\n', '_memset\n', ' U _memcpy\n'):
            with self.subTest(text=text):
                self.assertEqual(self.run_check(undefined=text).returncode, 0)

    def test_empty_or_unrelated_object_is_not_evidence(self):
        for text in ('', '00000 T some_other_function\n', ' U RealtimeState_process_block\n'):
            self.assertNotEqual(self.run_check(defined=text).returncode, 0)

    def test_forbidden_runtime_dependencies_are_rejected(self):
        for symbol in ('malloc', '_free', 'pthread_mutex_lock', 'write', '_panic', '__memset'):
            with self.subTest(symbol=symbol):
                result = self.run_check(undefined=f' U {symbol}\n')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('unreviewed', result.stderr)

    def test_unrecognized_nm_output_fails_closed(self):
        self.assertNotEqual(self.run_check(undefined='garbled symbol record\n').returncode, 0)


if __name__ == '__main__':
    unittest.main()
