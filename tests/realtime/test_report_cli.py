"""Known report fixtures test policy only, never pretend to be measurements."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT/'scripts/check-realtime-report.py'


def fixture(mode='dedicated'):
    return {'schemaVersion': 1, 'mode': mode, 'deviceId': 'unit-fixture-not-a-device',
            'cpu': 'synthetic-test-input', 'architecture': 'test', 'os': 'test',
            'compiler': 'test', 'kernel': 'scalar-f64', 'scene': 'c4-restrike-tail-v1',
            'warmupBlocks': 256, 'binaryBytes': 1000, 'modelBytes': 100,
            'sourceRevision': 'a'*40,
            'cases': [{'sampleRateHz': rate, 'blockFrames': size, 'observations': 100000,
                       'p50': .1, 'p99': .2, 'p9999': .3, 'max': .4, 'deadlineMisses': 0,
                       'activeModesPeak': 8, 'configuredModes': 8, 'activeStrings': 1,
                       'stateBytes': 1024, 'outputBytes': size*4, 'measurementBufferBytes': 800000}
                      for rate in (44100, 48000) for size in (64, 128, 256, 512)]}


class ReportContract(unittest.TestCase):
    def run_check(self, candidate, baseline=None, *, justification=False, enforce_budget=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root/'current.json'
            current.write_text(json.dumps(candidate))
            args = [sys.executable, str(CHECKER), str(current)]
            if enforce_budget:
                args.append('--enforce-budget')
            if baseline is not None:
                old = root/'previous.json'
                old.write_text(json.dumps(baseline))
                args += ['--baseline', str(old)]
                if justification:
                    benefit = {'baselineSha256': hashlib.sha256(old.read_bytes()).hexdigest(),
                               'candidateSha256': hashlib.sha256(current.read_bytes()).hexdigest(),
                               'acousticBenefit': 'unit test input only', 'reviewReference': 'test-review',
                               'errorMetrics': [{'name': 'test-error', 'unit': 'test', 'before': 2, 'after': 1}]}
                    path = root/'benefit.json'; path.write_text(json.dumps(benefit))
                    args += ['--change-report', str(path)]
            return subprocess.run(args, text=True, capture_output=True, timeout=5)

    def test_complete_matrix_is_accepted(self):
        result = self.run_check(fixture())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['validated'])

    def test_no_baseline_is_not_reported_as_zero_regressions(self):
        result = self.run_check(fixture('smoke'))
        summary = json.loads(result.stdout)
        self.assertIsNone(summary['regressions'])
        self.assertFalse(summary['absoluteBudgetChecked'])

    def test_explicit_budget_gate_without_a_baseline(self):
        current = fixture('smoke')
        accepted = self.run_check(current, enforce_budget=True)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        current['cases'][0].update(p9999=.9, max=.95)
        rejected = self.run_check(current, enforce_budget=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('absolute realtime contract', rejected.stderr)

    def test_deadline_count_must_agree_with_maximum(self):
        for maximum, misses in ((1.2, 0), (.4, 1)):
            current = fixture('smoke')
            current['cases'][0].update(max=maximum, deadlineMisses=misses)
            self.assertNotEqual(self.run_check(current).returncode, 0)

    def test_report_requires_an_actual_source_identity(self):
        current = fixture('smoke')
        current['sourceRevision'] = 'unknown'
        self.assertNotEqual(self.run_check(current).returncode, 0)

    def test_missing_case_is_rejected(self):
        current = fixture(); current['cases'].pop()
        self.assertNotEqual(self.run_check(current).returncode, 0)

    def test_nonfinite_or_false_type_is_rejected(self):
        for invalid in (float('nan'), float('inf'), True):
            current = fixture(); current['cases'][0]['p99'] = invalid
            self.assertNotEqual(self.run_check(current).returncode, 0)

    def test_hosted_smoke_is_not_a_dedicated_baseline(self):
        result = self.run_check(fixture('smoke'), fixture('smoke'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not release baselines', result.stderr)

    def test_different_hardware_is_not_compared(self):
        old = fixture(); current = copy.deepcopy(old); current['cpu'] = 'different'
        result = self.run_check(current, old)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('incomparable', result.stderr)

    def test_regression_requires_bound_acoustic_error_report(self):
        old = fixture(); current = copy.deepcopy(old); current['binaryBytes'] = 1500
        self.assertNotEqual(self.run_check(current, old).returncode, 0)
        self.assertEqual(self.run_check(current, old, justification=True).returncode, 0)

    def test_absolute_budget_cannot_be_waived(self):
        old = fixture(); current = copy.deepcopy(old)
        current['cases'][0].update(p9999=.9, max=.95)
        result = self.run_check(current, old, justification=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot waive', result.stderr)


if __name__ == '__main__':
    unittest.main()
