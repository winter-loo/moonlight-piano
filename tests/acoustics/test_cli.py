import json
import tempfile
import unittest
from pathlib import Path

from tools.acoustics.cli import create_report, main, validate_job
from tools.acoustics.fixtures import make_job


class EvidenceCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.manifest = make_job(cls.root/'fixtures')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_representative_report_is_reproducible_and_honest(self):
        report = create_report(self.manifest)
        other = create_report(self.manifest)
        self.assertEqual(report, other)
        self.assertEqual(report['evidenceKind'], 'synthetic-validation')
        self.assertEqual(len(report['cases']), 12)
        self.assertEqual(len(report['comparisons']), 3)
        for case in report['cases'][:3]:
            self.assertAlmostEqual(case['measurement']['decay']['late']['t60Seconds'], 6., delta=.3)
        json.dumps(report, allow_nan=False)
        near_far = report['comparisons'][1]['measurement']
        self.assertAlmostEqual(near_far['delaySeconds'], .001, delta=1/24000)
        self.assertAlmostEqual(near_far['gainDb'], -6.020599913, delta=.2)
        pedal = report['comparisons'][0]['measurement']
        self.assertAlmostEqual(pedal['lateT60DifferenceSeconds'], 5., delta=.5)
        self.assertGreater(report['comparisons'][2]['measurement']['baselineDifferenceDb'], 3)

    def test_fixture_regeneration_preserves_content_hashes(self):
        second = make_job(self.root/'another')
        self.assertEqual(json.loads(self.manifest.read_text()), json.loads(second.read_text()))

    def test_modified_recording_bytes_are_rejected(self):
        job = json.loads(self.manifest.read_text())
        job['cases'] = [job['cases'][0]]
        job['cases'][0]['recording']['sha256'] = '0'*64
        job['comparisons'] = []
        path = self.manifest.parent/'corrupted-job.json'
        path.write_text(json.dumps(job))
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            create_report(path)

    def test_outer_test_cannot_enter_report_pipeline(self):
        job = json.loads(self.manifest.read_text())
        job['cases'][0]['role'] = 'immutable-outer-test'
        with self.assertRaisesRegex(ValueError, 'outer-test'):
            validate_job(job)

    def test_cli_emits_json_and_markdown(self):
        job = json.loads(self.manifest.read_text())
        job['cases'] = [job['cases'][1]]
        job['comparisons'] = []
        path = self.manifest.parent/'one.json'
        path.write_text(json.dumps(job))
        output = self.root/'reports/one'
        main(['--manifest', str(path), '--output', str(output)])
        parsed = json.loads(Path(str(output)+'.json').read_text())
        self.assertEqual(parsed['toolVersion'], '0.1.0')
        self.assertIn('not LUFS', Path(str(output)+'.md').read_text())



    def test_pair_comparisons_require_appropriate_microphone_identities(self):
        original = json.loads(self.manifest.read_text())

        microphone_job = json.loads(self.manifest.read_text())
        microphone_job['cases'] = [
            case for case in microphone_job['cases']
            if case['id'] in {'mic-near', 'mic-far'}
        ]
        microphone_job['comparisons'] = [{
            'kind': 'microphones',
            'reference': 'mic-near',
            'changed': 'mic-far',
        }]
        for case in microphone_job['cases']:
            case['conditions']['microphone'] = 'same-mic'
        microphone_path = self.manifest.parent/'invalid-microphones.json'
        microphone_path.write_text(json.dumps(microphone_job))
        with self.assertRaisesRegex(ValueError, 'known distinct microphone identities'):
            create_report(microphone_path)

        sympathetic_job = original
        sympathetic_job['cases'] = [
            case for case in sympathetic_job['cases']
            if case['id'] in {'resonance-baseline', 'resonance-open-target'}
        ]
        sympathetic_job['comparisons'] = [{
            'kind': 'sympathetic',
            'reference': 'resonance-baseline',
            'changed': 'resonance-open-target',
            'targetHz': 392.,
            'startSeconds': 1.5,
            'endSeconds': 3.5,
            'targetWasStruck': False,
        }]
        sympathetic_job['cases'][1]['conditions']['microphone'] = 'other-mic'
        sympathetic_path = self.manifest.parent/'invalid-sympathetic.json'
        sympathetic_path.write_text(json.dumps(sympathetic_job))
        with self.assertRaisesRegex(ValueError, 'one known matched microphone'):
            create_report(sympathetic_path)


if __name__ == '__main__':
    unittest.main()
