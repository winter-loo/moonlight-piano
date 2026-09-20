import sys
import unittest
from pathlib import Path
import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from acoustics.comparison import compare_microphones, compare_pedal_states


class PairTests(unittest.TestCase):
    def test_known_microphone_delay_gain_and_phase(self):
        rate = 24000
        rng = np.random.default_rng(31)
        x = signal.sosfilt(signal.butter(3, [100, 3000], fs=rate, btype='bandpass', output='sos'), rng.normal(size=rate*2))
        y = np.concatenate([np.zeros(24), x[:-24]])*.5
        report = compare_microphones(x, y, rate, synchronized=True)
        self.assertAlmostEqual(report['delaySeconds'], .001, delta=1/rate)
        self.assertAlmostEqual(report['gainDb'], -6.0206, delta=.15)
        self.assertGreater(report['alignedCorrelation'], .99)
        self.assertTrue(report['crossSpectrum'])
        unavailable = compare_microphones(x, y, rate, synchronized=False)
        self.assertIsNone(unavailable['delaySeconds'])

    def test_pedal_pairs_require_controlled_conditions(self):
        base = {'conditions': {'note': 60, 'velocity': 80, 'pedal': 0, 'microphone': 'near', 'instrument': 'test'},
                'levels': {'rmsDbfs': -25}, 'decay': {'late': {'t60Seconds': 2}}}
        sustained = {'conditions': dict(base['conditions'], pedal=1),
                     'levels': {'rmsDbfs': -20}, 'decay': {'late': {'t60Seconds': 8}}}
        report = compare_pedal_states(base, sustained)
        self.assertEqual(report['lateT60DifferenceSeconds'], 6)
        self.assertEqual(report['levelDifferenceDb'], 5)
        sustained['conditions']['velocity'] = 100
        with self.assertRaises(ValueError):
            compare_pedal_states(base, sustained)


if __name__ == '__main__':
    unittest.main()
