"""Controlled-condition comparisons; explicitly refuse invalid causal claims."""
import numpy as np
from scipy import signal

from .analysis import _audio, _db


def compare_microphones(reference, other, rate, *, synchronized=False, max_delay_seconds=.02):
    a = _audio(reference, rate)
    b = _audio(other, rate)
    if len(a) != len(b):
        raise ValueError('microphone observations must cover the same frame interval')
    if not 0 < max_delay_seconds <= .1:
        raise ValueError('max delay must be in (0, 0.1] seconds')
    a, b = a[:, 0], b[:, 0]
    a = a-np.mean(a)
    b = b-np.mean(b)
    if np.linalg.norm(a) < 1e-12 or np.linalg.norm(b) < 1e-12:
        raise ValueError('microphone comparison needs nonzero AC energy')
    result = {'status': 'amplitude-only', 'gainDb': _db(np.sqrt(np.mean(b*b))/np.sqrt(np.mean(a*a))),
              'delaySeconds': None, 'alignedCorrelation': None, 'crossSpectrum': [],
              'limitation': 'room/microphone/directivity combined; not a measured board radiation operator'}
    if synchronized is not True:
        result['reason'] = 'different takes or unknown synchronization: phase/delay are not identifiable'
        return result
    bound = round(rate*max_delay_seconds)
    correlation = signal.correlate(b, a, mode='full', method='fft')
    center = len(a)-1
    local = correlation[center-bound:center+bound+1]
    delay = int(np.argmax(np.abs(local)))-bound
    if delay >= 0:
        aa, bb = a[:len(a)-delay], b[delay:]
    else:
        aa, bb = a[-delay:], b[:len(b)+delay]
    coefficient = float(np.dot(aa, bb)/np.sqrt(np.dot(aa, aa)*np.dot(bb, bb)))
    # The correlation estimate is ambiguous for a periodic tone. Report that,
    # rather than calling one arbitrarily selected lag a physical distance.
    peaks, _ = signal.find_peaks(np.abs(local))
    candidates = sorted((float(abs(local[k])), int(k)) for k in peaks)[::-1]
    ambiguity = len(candidates) > 1 and candidates[1][0] > candidates[0][0]*.98
    nperseg = min(4096, len(a)//4)
    frequency, cross = signal.csd(a, b, fs=rate, nperseg=nperseg)
    _, power_a = signal.welch(a, fs=rate, nperseg=nperseg)
    _, coherence = signal.coherence(a, b, fs=rate, nperseg=nperseg)
    valid = np.where((frequency > 20) & (power_a > np.max(power_a)*1e-4))[0]
    stride = max(1, len(valid)//96)
    features = [{'hz': float(frequency[k]), 'phaseRadians': float(np.angle(cross[k])),
                 'transferGainDb': _db(abs(cross[k])/max(power_a[k], 1e-30)),
                 'coherence': float(np.clip(coherence[k], 0, 1))} for k in valid[::stride]]
    result.update(status='measured', delaySeconds=delay/rate, delayResolutionSeconds=1/rate,
                  delayAmbiguous=ambiguity, alignedCorrelation=coefficient,
                  synchronization='declared-same-take', crossSpectrum=features)
    return result


def compare_pedal_states(reference, changed):
    ca, cb = reference['conditions'], changed['conditions']
    for field in ('note', 'velocity', 'microphone', 'instrument'):
        if ca.get(field) is None or ca.get(field) != cb.get(field):
            raise ValueError(f'controlled pedal comparison requires matched known {field}')
    if ca.get('pedal') is None or cb.get('pedal') is None or ca['pedal'] == cb['pedal']:
        raise ValueError('two explicitly distinct pedal states are required')
    a = reference['decay']['late'].get('t60Seconds')
    b = changed['decay']['late'].get('t60Seconds')
    return {'referencePedal': ca['pedal'], 'changedPedal': cb['pedal'],
            'levelDifferenceDb': changed['levels']['rmsDbfs']-reference['levels']['rmsDbfs'],
            'lateT60DifferenceSeconds': b-a if a is not None and b is not None else None,
            'interpretation': 'state-specific observation, not an isolated room reverb measurement'}


def measure_sympathetic_resonance(samples, rate, *, target_hz, start_seconds, end_seconds,
                                 target_was_struck, baseline=None):
    """Measure energy near an explicitly unstruck open string, not infer intent."""
    audio = _audio(samples, rate)[:, 0]
    if target_was_struck is not False:
        raise ValueError('explicit evidence that the target string was not struck is required')
    if not 20 < target_hz < rate*.49 or not 0 <= start_seconds < end_seconds <= len(audio)/rate:
        raise ValueError('invalid resonance band or time window')
    if end_seconds-start_seconds < .02:
        raise ValueError('resonance observation must be at least 20ms')
    band = signal.butter(3, [target_hz-5, target_hz+5], fs=rate, btype='bandpass', output='sos')
    filtered = signal.sosfiltfilt(band, audio)
    interval = slice(round(start_seconds*rate), round(end_seconds*rate))
    rms = float(np.sqrt(np.mean(filtered[interval]**2)))
    result = {'status': 'measured', 'targetHz': target_hz, 'bandWidthHz': 10,
              'startSeconds': start_seconds, 'endSeconds': end_seconds, 'rmsDbfs': _db(rms),
              'limitation': 'band energy may include overlapping partials; causal resonance needs a controlled baseline'}
    if baseline is not None:
        dry = _audio(baseline, rate)[:, 0]
        if len(dry) != len(audio):
            raise ValueError('baseline interval mismatch')
        base = signal.sosfiltfilt(band, dry)[interval]
        result['baselineDifferenceDb'] = _db(rms)-_db(np.sqrt(np.mean(base**2)))
    return result
