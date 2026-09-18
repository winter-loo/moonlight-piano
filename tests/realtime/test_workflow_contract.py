"""Regression guards for known CI command, provenance and coverage mistakes."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class WorkflowContract(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / '.github/workflows/realtime-safety.yml').read_text()

    def test_bash_renderer_and_all_deterministic_artifacts_are_checked(self):
        self.assertNotRegex(self.text, r'(?<![a-z])sh scripts/render-physical-c4\.sh')
        self.assertEqual(self.text.count('bash scripts/render-physical-c4.sh'), 2)
        for name in ('c4-reference.wav', 'c4-report.json', 'c4-energy.csv'):
            self.assertIn(f'cmp work/c4-a/{name} work/c4-b/{name}', self.text)

    def test_evidence_identifies_the_checked_out_commit(self):
        self.assertIn('MOONLIGHT_SOURCE_REVISION="$(git rev-parse HEAD)"', self.text)
        self.assertNotIn('github.event.pull_request.head.sha', self.text)
        self.assertIn('realtime-evidence-${{ github.sha }}', self.text)

    def test_guards_stay_read_only_and_cover_their_own_inputs(self):
        self.assertIn('contents: read', self.text)
        self.assertIn('persist-credentials: false', self.text)
        self.assertNotIn('git push', self.text)
        for pattern in ('fixtures/physical-c4/**', 'scripts/render-physical-c4.sh', 'tests/realtime/**'):
            self.assertGreaterEqual(self.text.count(pattern), 2)
        self.assertIn('cargo test --release -p moonlight-dsp --test realtime_contract', self.text)
        self.assertIn('python3 -m unittest discover -s tests/realtime -v', self.text)


if __name__ == '__main__':
    unittest.main()
