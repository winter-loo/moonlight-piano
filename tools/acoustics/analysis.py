"""Explicit, uncertainty-bearing measurements of isolated piano recordings.

Frequency tracks use Hann windows and interpolated FFT peaks. Decay fits are
observations, not identified felt/material constants. No room/board separation
is claimed from a single microphone. Missing experimental metadata stays null.
"""
from dataclasses import dataclass
import math

import numpy as np
from scipy import signal, stats

MAX_DECODED_SCALARS = 16_000_000


@dataclass(frozen=True)
class AnalysisConfig:
    max_partials: int = 12
    guard_ratio: float = 0.98
    envelope_seconds: float = 0.005
    track_seconds: float = 0.5
    hop_seconds: float = 0.25
    peak_floor_db: float = -55.0

    def validate(self):
        if type(self.max_partials) is not int or not 1 <= self.max_partials <= 128:
            raise ValueError('max_partials must be 1..128')
        if not 0.5 <= self.guard_ratio < 1:
            raise ValueError('guard_ratio must be in [0.5, 1)')
        if not 0.001 <= self.envelope_seconds <= 0.05:
            raise ValueError('invalid envelope window')
        if not 0.1 <= self.track_seconds <= 4 or not 0.025 <= self.hop_seconds <= 2:
            raise ValueError('invalid track/hop duration')
        if not -120 <= self.peak_floor_db <= -10:
            raise ValueError('invalid peak floor')


def _audio(samples, rate):
    x = np.asarray(samples, dtype=np.float64)
    if isinstance(rate, bool) or not isinstance(rate, (int, np.integer)) or not 8000 <= rate <= 384000:
        raise ValueError('sample rate must be an integer in 8000..384000')
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or not 1 <= x.shape[1] <= 8:
        raise ValueError('audio must be frames by channels (1..8 channels)')
    if x.size > MAX_DECODED_SCALARS:
        raise ValueError('decoded audio exceeds scalar memory budget')
    if not rate // 5 <= len(x) <= 120 * rate or not np.isfinite(x).all():
        raise ValueError('audio must be finite and 0.2..120 seconds long')
    if np.max(np.abs(x-np.mean(x, axis=0))) < 1e-9:
        raise ValueError('silent or DC-only recording cannot identify acoustic features')
    return x


def _db(value):
    return float(20 * np.log10(max(float(value), 1e-15)))


def _spectrum(x, rate):
    n = len(x)
    fft_size = 1 << math.ceil(math.log2(max(64, n * 4)))
    window = signal.windows.hann(n, sym=False)
    magnitude = np.abs(np.fft.rfft((x - np.mean(x)) * window, n=fft_size))
    return np.fft.rfftfreq(fft_size, 1 / rate), magnitude


def _peak(freqs, magnitude, target, radius, ceiling, floor):
    candidates, _ = signal.find_peaks(magnitude)
    valid = candidates[(freqs[candidates] >= max(1, target - radius)) &
                       (freqs[candidates] <= min(ceiling, target + radius)) &
                       (magnitude[candidates] >= floor)]
    if not len(valid):
        return None
    k = int(valid[np.argmax(magnitude[valid])])
    a, b, c = np.log(np.maximum(magnitude[k-1:k+2], 1e-300))
    divisor = a - 2*b + c
    offset = 0.5*(a-c)/divisor if abs(divisor) > 1e-15 else 0.0
    offset = float(np.clip(offset, -.5, .5))
    return {'hz': float(freqs[k] + offset*(freqs[1]-freqs[0])),
            'amplitude': float(magnitude[k])}


def _envelope(x, rate, seconds):
    size = max(1, round(rate * seconds))
    count = len(x) // size
    blocks = x[:count*size].reshape(count, size)
    return (np.arange(count) + .5)*size/rate, np.sqrt(np.mean(blocks**2, axis=1)), size/rate


def _decay(times, envelope, start, end):
    mask = (times >= start) & (times <= end) & (envelope > max(np.max(envelope)*1e-4, 1e-12))
    t = times[mask]
    values = envelope[mask]
    if len(t) < 12 or t[-1]-t[0] < .1:
        return {'status': 'unavailable', 'reason': 'insufficient above-floor decay duration'}
    fitted = stats.linregress(t, 20*np.log10(values))
    slope = float(fitted.slope)
    return {'status': 'measured', 'startSeconds': float(t[0]), 'endSeconds': float(t[-1]),
            'slopeDbPerSecond': slope, 'slopeStandardError': float(fitted.stderr),
            'rSquared': float(fitted.rvalue**2),
            't60Seconds': -60/slope if slope < -.05 and fitted.rvalue**2 >= .8 else None,
            't60IsExtrapolation': True,
            'method': 'OLS amplitude-dB slope; correlated windows are not independent trials'}


def _beating(x, rate, f0):
    duration = len(x) / rate
    if duration < 1.5 or f0 <= 15 or f0 + 12 >= rate/2:
        return {'status': 'unavailable', 'reason': 'need >=1.5 seconds around a resolvable fundamental'}
    sos = signal.butter(3, [f0-12, f0+12], btype='bandpass', fs=rate, output='sos')
    envelope = np.abs(signal.hilbert(signal.sosfiltfilt(sos, x)))
    step = max(1, rate//100)
    envelope = envelope[round(.2*rate):-round(.2*rate):step]
    if len(envelope) < 50:
        return {'status': 'unavailable', 'reason': 'too little edge-free signal'}
    log_envelope = np.log(np.maximum(envelope, 1e-12))
    residual = signal.detrend(log_envelope)
    modulation = float(np.percentile(residual, 95)-np.percentile(residual, 5))
    freqs, spectrum = _spectrum(residual, rate/step)
    low = max(.5, 3/(len(residual)*step/rate))
    indices = np.where((freqs >= low) & (freqs <= 10))[0]
    if not len(indices) or modulation < .08:
        return {'status': 'not-detected', 'upperSensitivityLogAmplitude': .08}
    k = indices[np.argmax(spectrum[indices])]
    prominence = float(spectrum[k] / max(np.median(spectrum[indices]), 1e-12))
    if prominence < 5:
        return {'status': 'not-detected', 'reason': 'no prominent periodic envelope component'}
    return {'status': 'candidate', 'hz': float(freqs[k]),
            'frequencyResolutionHz': float(1/(len(residual)*step/rate)),
            'logAmplitudeRange': modulation,
            'limitation': 'AM, reflections and unison beating are not uniquely distinguishable'}


def analyze_note(samples, rate, conditions, *, rendered_rate=None, config=None):
    config = config or AnalysisConfig()
    config.validate()
    x = _audio(samples, rate)
    rendered_rate = rate if rendered_rate is None else rendered_rate
    if isinstance(rendered_rate, bool) or not isinstance(rendered_rate, int) or not 8000 <= rendered_rate <= 384000:
        raise ValueError('rendered_rate must be an integer in 8000..384000')
    if not isinstance(conditions, dict):
        raise ValueError('recording conditions must be an object')
    note = conditions.get('note')
    if isinstance(note, bool) or not isinstance(note, int) or not 0 <= note <= 127:
        raise ValueError('a known MIDI note is required; it is a search prior, not a measured frequency')
    nominal = 440*2**((note-69)/12)
    ceiling = min(rate, rendered_rate)*.5*config.guard_ratio
    if nominal >= ceiling:
        raise ValueError('fundamental lies outside common guarded bandwidth')
    # Avoid cancellation in anti-phase stereo: measure the highest-energy channel.
    channel = int(np.argmax(np.mean(x*x, axis=0)))
    mono = x[:, channel]
    times, envelope, envelope_step = _envelope(mono, rate, config.envelope_seconds)
    peak_index = int(np.argmax(envelope))
    peak = envelope[peak_index]
    onset_index = int(np.flatnonzero(envelope >= peak*.01)[0])
    onset = max(0.0, float(times[onset_index] - envelope_step/2))
    crossing10 = np.flatnonzero(envelope[:peak_index+1] >= peak*.1)
    crossing90 = np.flatnonzero(envelope[:peak_index+1] >= peak*.9)
    attack = float(times[crossing90[0]] - times[crossing10[0]])
    release = conditions.get('noteOffSeconds')
    if release is not None and (not isinstance(release, (float, int)) or isinstance(release, bool)
                                or not math.isfinite(release) or not onset < release < len(x)/rate):
        raise ValueError('noteOffSeconds must be finite and within the audible recording')
    sustain_end = release if release is not None else len(x)/rate
    post_onset_seconds = sustain_end - onset
    if post_onset_seconds < .1:
        raise ValueError('insufficient post-onset material for stable analysis')
    # Start after the detected onset while preserving at least 100 ms of
    # post-onset material for short notes.
    analysis_start = onset + min(.08, max(0., post_onset_seconds-.1))
    analysis_end = min(sustain_end, analysis_start+4)
    segment = mono[round(analysis_start*rate):round(analysis_end*rate)]
    if len(segment) < rate*.1:
        raise ValueError('insufficient stable analysis interval')
    frequencies, spectrum = _spectrum(segment, rate)
    guarded = frequencies < ceiling
    spectral_power = spectrum**2
    guarded_power = float(np.sum(spectral_power[guarded]))
    if not math.isfinite(guarded_power) or guarded_power <= 1e-24:
        raise ValueError('stable analysis interval has no spectral energy')
    floor = np.max(spectrum[guarded]) * 10**(config.peak_floor_db/20)
    frequency_resolution = rate/len(segment)
    fundamental = _peak(frequencies, spectrum, nominal, nominal*.055, ceiling, floor)
    reference_f0 = fundamental['hz'] if fundamental else nominal
    partials = []
    for n in range(1, config.max_partials+1):
        target = n*reference_f0
        if target >= ceiling:
            break
        found = _peak(frequencies, spectrum, target, min(reference_f0*.4, target*.055), ceiling, floor)
        if found is None:
            continue
        tracks = []
        window = round(config.track_seconds*rate)
        hop = round(config.hop_seconds*rate)
        for start in range(round(analysis_start*rate), round(sustain_end*rate)-window+1, hop):
            frame_freq, frame_spec = _spectrum(mono[start:start+window], rate)
            frame_peak = _peak(frame_freq, frame_spec, found['hz'], max(3, frequency_resolution*3),
                               ceiling, np.max(frame_spec)*10**(config.peak_floor_db/20))
            if frame_peak:
                tracks.append({'seconds': float((start+window/2)/rate), 'hz': frame_peak['hz'],
                               'relativeDb': _db(frame_peak['amplitude'] / max(np.sum(signal.windows.hann(window, sym=False))/2, 1))})
        partials.append({'index': n, 'hz': found['hz'], 'resolutionHz': frequency_resolution,
                         'relativeDb': _db(found['amplitude']/np.max(spectrum)), 'track': tracks})
    inharmonicity = {'status': 'unavailable', 'reason': 'need at least three resolved partials'}
    if len(partials) >= 3:
        ns = np.array([item['index'] for item in partials], dtype=float)
        ys = np.array([(item['hz']/item['index'])**2 for item in partials])
        fit = stats.linregress(ns*ns, ys)
        if fit.intercept > 0 and 0 <= fit.slope/fit.intercept <= .02:
            inharmonicity = {'status': 'estimated', 'B': float(fit.slope/fit.intercept),
                            'idealStringFrequencyHz': float(np.sqrt(fit.intercept)),
                            'rSquared': float(fit.rvalue**2),
                            'slopeStandardError': float(fit.stderr),
                            'limitation': 'equivalent stiff-string fit; not unique tension/length identification'}
    decay_start = max(float(times[peak_index])+.08, onset+.15)
    middle = decay_start + max(0, sustain_end-decay_start)*.45
    centroid = float(np.sum(frequencies[guarded]*spectral_power[guarded])/guarded_power)
    pre = mono[:max(0, round(onset*rate))]
    noise = {'status': 'unavailable', 'reason': 'no >=20ms pre-onset observation; cannot isolate mechanical noise'}
    if len(pre) >= .02*rate:
        noise = {'status': 'measured', 'preOnsetRmsDbfs': _db(np.sqrt(np.mean(pre*pre))),
                 'limitation': 'ambient/recording floor, not identified hammer noise'}
    decay_times, decay_envelope, decay_step = _envelope(mono, rate, max(.025, 3/reference_f0))
    release_result = {'status': 'unavailable', 'reason': 'note-off timestamp not supplied'}
    if release is not None:
        release_result = {'status': 'measured', 'noteOffSeconds': release,
                          'decay': _decay(decay_times, decay_envelope, release+decay_step/2, len(x)/rate)}
    return {'schemaVersion': 1, 'conditions': dict(conditions), 'sourceRateHz': rate,
            'renderedRateHz': rendered_rate, 'frames': len(x), 'channels': x.shape[1],
            'analysisChannel': channel, 'commonGuardedNyquistHz': ceiling,
            'fundamental': {'status': 'measured' if fundamental else 'unavailable',
                            'hz': fundamental['hz'] if fundamental else None,
                            'nominalSearchPriorHz': nominal, 'resolutionHz': frequency_resolution},
            'partials': partials, 'inharmonicity': inharmonicity,
            'attack': {'onsetSeconds': onset, 'rise10To90Seconds': attack,
                       'resolutionSeconds': envelope_step},
            'stableAnalysisInterval': {'startSeconds': float(analysis_start),
                                       'endSeconds': float(analysis_end)},
            'decay': {'envelopeResolutionSeconds': decay_step,
                      'early': _decay(decay_times, decay_envelope, decay_start, middle),
                      'late': _decay(decay_times, decay_envelope, middle, sustain_end-decay_step/2)},
            'levels': {'rmsDbfs': _db(np.sqrt(np.mean(x*x))),
                       'peakDbfs': _db(np.max(np.abs(x))),
                       'integratedLufs': None, 'lufsReason': 'RMS is not BS.1770 perceptual loudness'},
            'spectralCentroidHz': centroid,
            'beating': _beating(segment, rate, reference_f0), 'release': release_result, 'noise': noise,
            'uncertainty': ['FFT padding interpolates peaks; it creates neither bandwidth nor observation time.',
                            'Quoted frequency resolution is 1/window duration, not a confidence interval.',
                            'Single-microphone recordings cannot uniquely separate strings, board and room.']}
