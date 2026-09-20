"""Reproducible estimator fixtures. These are not a physical piano engine."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from . import __version__


def make_job(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rate = 24000
    t = np.arange(rate*5)/rate
    cases = []

    def add(name, samples, conditions, truth, sample_rate=rate, **metadata):
        path = directory/(name+'.wav')
        sf.write(path, samples, sample_rate, subtype='PCM_24')
        data = path.read_bytes()
        cases.append({'id': name, 'role': 'synthetic-validation', 'conditions': conditions,
                      'recording': {'path': path.name, 'bytes': len(data),
                                    'sha256': hashlib.sha256(data).hexdigest()},
                      'provenance': {'generator': 'tools.acoustics.fixtures', 'version': __version__,
                                     'seed': 1729, 'groundTruth': truth,
                                     'license': 'project-generated-estimator-fixture',
                                     'purpose': 'estimator validation only; not a measured piano'}, **metadata})

    def tone(note, decay=6., strength=.15, brightness=.55):
        base = 440*2**((note-69)/12)
        b = .0002
        env = np.where(t >= .1, (1-np.exp(-np.maximum(t-.1, 0)/.006))*10**(-3*np.maximum(t-.1, 0)/decay), 0.)
        x = np.zeros_like(t)
        for n in range(1, 9):
            frequency = n*base*np.sqrt(1+b*n*n)
            if frequency < rate*.48:
                x += strength*brightness**(n-1)*env*np.sin(2*np.pi*frequency*(t-.1))
        return x

    for name, note in [('bass', 36), ('midrange', 60), ('treble', 96)]:
        add(name, tone(note), {'note': note, 'velocity': .6, 'pedal': 0., 'microphone': 'fixture',
                              'instrument': 'analytic-stiff-partials'},
            {'inharmonicity': .0002, 't60Seconds': 6., 'onsetSeconds': .1})
    for name, velocity, strength, brightness in [('soft', .2, .03, .3), ('strong', .9, .2, .7)]:
        add(name, tone(60, strength=strength, brightness=brightness),
            {'note': 60, 'velocity': velocity, 'pedal': 0., 'microphone': 'fixture',
             'instrument': 'analytic-stiff-partials'}, {'t60Seconds': 6., 'onsetSeconds': .1})
    for name, pedal, decay in [('pedal-up', 0., 2.), ('pedal-down', 1., 7.)]:
        add(name, tone(60, decay=decay), {'note': 60, 'velocity': .6, 'pedal': pedal,
                                      'microphone': 'fixture', 'instrument': 'analytic-stiff-partials'},
            {'t60Seconds': decay, 'onsetSeconds': .1})
    # Broadband component disambiguates periodic lag peaks in this known same take.
    rng = np.random.default_rng(1729)
    broadband = signal.sosfilt(signal.butter(4, [500, 6000], fs=rate, btype='bandpass', output='sos'), rng.normal(size=len(t)))
    a = tone(60)+.01*broadband
    b = np.concatenate([np.zeros(24), .5*a[:-24]])
    for name, samples, mic in [('mic-near', a, 'near'), ('mic-far', b, 'far')]:
        add(name, samples, {'note': 60, 'velocity': .6, 'pedal': 0., 'microphone': mic,
                           'instrument': 'analytic-stiff-partials'},
            {'pairDelaySeconds': .001, 'pairGainDb': -6.020599913}, synchronizedTakeId='fixture-take-1729')
    dry = tone(48)
    # Target near G4 is explicitly not struck: this fixture supplies intent.
    response = .01*np.sin(2*np.pi*392*t)*np.where(t >= 1, 10**(-np.maximum(t-1, 0)/3), 0)
    for name, samples in [('resonance-baseline', dry), ('resonance-open-target', dry+response)]:
        add(name, samples, {'note': 48, 'velocity': .6, 'pedal': 1., 'microphone': 'fixture',
                           'instrument': 'analytic-stiff-partials'}, {'unstruckTargetHz': 392., 'windowSeconds': [1.5, 3.5]})
    # An actual high sample-rate signal, not upsampling of a low-rate recording.
    high_rate = 96000
    ht = np.arange(high_rate*2)/high_rate
    base = 4186.0090448
    high = .1*np.sin(2*np.pi*base*ht)+.03*np.sin(2*np.pi*8*base*ht)
    add('native-96k-treble', high, {'note': 108, 'velocity': .6, 'pedal': 0.,
                                  'microphone': 'fixture', 'instrument': 'analytic-high-rate'},
        {'fundamentalHz': base, 'eighthPartialHz': 8*base}, sample_rate=high_rate)
    job = {'schemaVersion': 1, 'evidenceKind': 'synthetic-validation', 'cases': cases,
           'comparisons': [
               {'kind': 'pedal', 'reference': 'pedal-up', 'changed': 'pedal-down'},
               {'kind': 'microphones', 'reference': 'mic-near', 'changed': 'mic-far'},
               {'kind': 'sympathetic', 'reference': 'resonance-baseline', 'changed': 'resonance-open-target',
                'targetHz': 392., 'startSeconds': 1.5, 'endSeconds': 3.5, 'targetWasStruck': False}]}
    path = directory/'job.json'
    path.write_text(json.dumps(job, indent=2, sort_keys=True, allow_nan=False)+'\n')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('work/acoustic-analysis/fixtures'))
    print(make_job(parser.parse_args().output))


if __name__ == '__main__':
    main()
