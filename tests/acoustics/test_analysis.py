import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from acoustics.analysis import analyze_note


class NoteAnalysisTests(unittest.TestCase):
    def test_known_sine_frequency_and_silent_input(self):
        rate = 24000
        t = np.arange(rate * 3) / rate
        signal = .3 * (1 - np.exp(-t / .005)) * np.exp(-t) * np.sin(2*np.pi*440*t)
        report = analyze_note(signal, rate, {'note': 69}, rendered_rate=48000)
        self.assertAlmostEqual(report['fundamental']['hz'], 440, delta=.3)
        with self.assertRaises(ValueError):
            analyze_note(np.zeros(rate), rate, {'note': 69})



class ControlledFeatureTests(unittest.TestCase):
    def test_stiff_partials_and_known_decay(self):
        rate = 24000
        t = np.arange(rate*5)/rate
        b = .00025
        x = sum((1/n)*np.sin(2*np.pi*n*220*np.sqrt(1+b*n*n)*t) for n in range(1, 9))
        x *= .2*(1-np.exp(-t/.005))*np.exp(-np.log(1000)*t/6)
        report = analyze_note(x, rate, {'note': 57})
        self.assertAlmostEqual(report['inharmonicity']['B'], b, delta=2e-5)
        self.assertAlmostEqual(report['decay']['late']['t60Seconds'], 6, delta=.25)
        self.assertGreater(len(report['partials'][0]['track']), 3)

    def test_source_and_render_bandwidth_are_both_obeyed(self):
        rate = 96000
        t = np.arange(rate)/rate
        x = .2*np.sin(2*np.pi*4186.009*t) + .1*np.sin(2*np.pi*8*4186.009*t)
        realtime = analyze_note(x, rate, {'note': 108}, rendered_rate=48000)
        reference = analyze_note(x, rate, {'note': 108}, rendered_rate=96000)
        self.assertTrue(all(p['hz'] < 23520 for p in realtime['partials']))
        self.assertTrue(any(p['index'] == 8 for p in reference['partials']))

    def test_release_is_not_invented_and_known_noteoff_has_own_fit(self):
        rate = 24000
        t = np.arange(rate*4)/rate
        x = .3*(1-np.exp(-t/.005))*np.sin(2*np.pi*440*t)
        x *= np.exp(-t/3)*np.exp(-np.maximum(0, t-2)*8)
        unknown = analyze_note(x, rate, {'note': 69})
        known = analyze_note(x, rate, {'note': 69, 'noteOffSeconds': 2})
        self.assertEqual(unknown['release']['status'], 'unavailable')
        self.assertAlmostEqual(known['release']['decay']['t60Seconds'], .829, delta=.08)

    def test_periodic_envelope_is_reported_as_candidate_not_proven_unison(self):
        rate = 24000
        t = np.arange(rate*5)/rate
        x = .2*(1+.4*np.cos(2*np.pi*3*t))*np.sin(2*np.pi*440*t)*np.exp(-t/4)
        report = analyze_note(x, rate, {'note': 69})
        self.assertEqual(report['beating']['status'], 'candidate')
        self.assertAlmostEqual(report['beating']['hz'], 3, delta=.3)

    def test_nonfinite_and_invalid_conditions_fail_closed(self):
        rate = 24000
        t = np.arange(rate)/rate
        x = np.sin(2*np.pi*440*t)
        for value in [float('nan'), float('inf')]:
            broken = x.copy()
            broken[3] = value
            with self.assertRaises(ValueError):
                analyze_note(broken, rate, {'note': 69})
        with self.assertRaises(ValueError):
            analyze_note(x, rate, {'note': 69, 'noteOffSeconds': float('nan')})

    def test_antiphase_stereo_does_not_cancel_pitch_estimate(self):
        rate = 24000
        t = np.arange(rate*2)/rate
        x = .1*np.sin(2*np.pi*440*t)
        result = analyze_note(np.column_stack([x, -x]), rate, {'note': 69})
        self.assertAlmostEqual(result['fundamental']['hz'], 440, delta=.3)


    def test_short_released_note_keeps_stable_window_after_detected_onset(self):
        rate = 24000
        duration = 2
        x = np.zeros(rate * duration)
        start = rate
        stop = round(1.25 * rate)
        t = np.arange(stop-start) / rate
        x[start:stop] = .3 * np.sin(2*np.pi*440*t)
        report = analyze_note(x, rate, {'note': 69, 'noteOffSeconds': 1.25})
        interval = report['stableAnalysisInterval']
        self.assertGreaterEqual(interval['startSeconds'], report['attack']['onsetSeconds'])
        self.assertLessEqual(interval['endSeconds'], 1.25)
        self.assertAlmostEqual(report['fundamental']['hz'], 440, delta=1.0)

    def test_attack_only_recording_rejects_empty_stable_spectrum(self):
        rate = 24000
        x = np.zeros(rate)
        active = round(.05 * rate)
        t = np.arange(active) / rate
        x[:active] = .3 * np.sin(2*np.pi*440*t)
        with self.assertRaisesRegex(ValueError, 'stable analysis interval has no spectral energy'):
            analyze_note(x, rate, {'note': 69})


if __name__ == '__main__':
    unittest.main()
