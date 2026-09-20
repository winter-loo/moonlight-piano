"""Render JSON/Markdown evidence from an integrity-checked analysis job.

Jobs for registered audio are prepared by scripts/prepare-acoustic-analysis.mjs.
The hash binds bytes, not a license opinion: the source registry remains the
licensing authority. Synthetic jobs exercise estimators, never piano realism.
"""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import platform
import shlex

import numpy as np
import scipy
import soundfile as sf

from . import __version__
from .analysis import AnalysisConfig, analyze_note, MAX_DECODED_SCALARS
from .comparison import compare_microphones, compare_pedal_states, measure_sympathetic_resonance

MAX_FILE_BYTES = 256 * 1024 * 1024
ROLES = {'calibration', 'development-validation', 'cross-piano-validation', 'synthetic-validation'}


def read_case(case, job_directory):
    if case.get('role') not in ROLES:
        raise ValueError('analysis is restricted to inspectable development evidence; no outer-test role')
    recording = case['recording']
    source_path = (job_directory / recording['path']).resolve()
    if not 0 < source_path.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError('recording byte size is outside the analysis budget')
    content = source_path.read_bytes()
    if len(content) != recording['bytes'] or hashlib.sha256(content).hexdigest() != recording['sha256']:
        raise ValueError('recording bytes differ from the prepared evidence')
    # Decode the already-checked bytes, not a second path open that could change.
    with sf.SoundFile(io.BytesIO(content)) as audio:
        if not 8000 <= audio.samplerate <= 384000 or not 1 <= audio.channels <= 8:
            raise ValueError('unsupported recording format')
        if not .2 <= len(audio) / audio.samplerate <= 120:
            raise ValueError('recording duration exceeds analysis budget')
        if len(audio)*audio.channels > MAX_DECODED_SCALARS:
            raise ValueError('decoded recording exceeds scalar memory budget')
        samples = audio.read(dtype='float64', always_2d=True)
        rate = int(audio.samplerate)
    return samples, rate


def validate_job(job):
    if job.get('schemaVersion') != 1 or job.get('evidenceKind') not in ('registered-reference', 'synthetic-validation'):
        raise ValueError('unsupported analysis job')
    cases = job.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise ValueError('an analysis job requires 1..32 cases')
    ids = set()
    for case in cases:
        name = case.get('id')
        if not isinstance(name, str) or not name or name in ids:
            raise ValueError('case IDs must be unique nonempty strings')
        ids.add(name)
        if case.get('role') not in ROLES:
            raise ValueError('outer-test evidence must never enter development analysis')
        provenance = case.get('provenance')
        if not isinstance(provenance, dict) or not provenance:
            raise ValueError('case provenance is required')
        if job['evidenceKind'] == 'registered-reference':
            if case['role'] == 'synthetic-validation':
                raise ValueError('registered audio cannot pretend to be a synthetic fixture')
            for key in ('sourceId', 'assetId', 'license', 'attribution', 'origin', 'registrySha256'):
                if not provenance.get(key):
                    raise ValueError(f'missing reference provenance {key}')
        elif case['role'] != 'synthetic-validation':
            raise ValueError('synthetic evidence is not a piano calibration source')
    comparisons = job.get('comparisons', [])
    if not isinstance(comparisons, list) or len(comparisons) > 32:
        raise ValueError('comparison budget exceeded')
    for comparison in comparisons:
        if comparison.get('reference') not in ids or comparison.get('changed') not in ids:
            raise ValueError('comparison must refer to cases in this job')
        if comparison['reference'] == comparison['changed']:
            raise ValueError('comparison requires distinct observations')
        if comparison.get('kind') not in ('pedal', 'microphones', 'sympathetic'):
            raise ValueError('unsupported comparison')
    return job


def create_report(job_path, *, rendered_rate=48000, config=None, command=None):
    job_path = Path(job_path).resolve()
    if job_path.stat().st_size > 1024 * 1024:
        raise ValueError('job metadata too large')
    job_bytes = job_path.read_bytes()
    job = validate_job(json.loads(job_bytes))
    config = config or AnalysisConfig()
    results = []
    by_id = {case['id']: case for case in job['cases']}
    for case in job['cases']:
        samples, rate = read_case(case, job_path.parent)
        measurement = analyze_note(samples, rate, case['conditions'], rendered_rate=rendered_rate, config=config)
        results.append({'id': case['id'], 'role': case['role'], 'provenance': case['provenance'],
                        'recordingSha256': case['recording']['sha256'], 'measurement': measurement})
    measurements = {case['id']: case['measurement'] for case in results}
    comparisons = []
    for item in job.get('comparisons', []):
        reference = by_id[item['reference']]
        changed = by_id[item['changed']]
        if item['kind'] == 'pedal':
            value = compare_pedal_states(measurements[reference['id']], measurements[changed['id']])
        else:
            a, rate = read_case(reference, job_path.parent)
            b, other_rate = read_case(changed, job_path.parent)
            if rate != other_rate:
                raise ValueError('paired observations require the same native sample rate')
            for key in ('note', 'velocity', 'pedal', 'instrument'):
                if reference['conditions'].get(key) is None or reference['conditions'][key] != changed['conditions'].get(key):
                    raise ValueError(f'paired observations need matched known {key}')
            reference_mic = reference['conditions'].get('microphone')
            changed_mic = changed['conditions'].get('microphone')
            reference_mic_known = isinstance(reference_mic, str) and bool(reference_mic.strip())
            changed_mic_known = isinstance(changed_mic, str) and bool(changed_mic.strip())
            if item['kind'] == 'microphones':
                if not reference_mic_known or not changed_mic_known or reference_mic == changed_mic:
                    raise ValueError('microphone comparison requires known distinct microphone identities')
                sync_group = reference.get('synchronizedTakeId')
                synchronized = bool(sync_group) and sync_group == changed.get('synchronizedTakeId')
                value = compare_microphones(a, b, rate, synchronized=synchronized)
            else:
                if not reference_mic_known or not changed_mic_known or reference_mic != changed_mic:
                    raise ValueError('sympathetic comparison requires one known matched microphone')
                value = measure_sympathetic_resonance(
                    b, rate, baseline=a, target_hz=item['targetHz'],
                    start_seconds=item['startSeconds'], end_seconds=item['endSeconds'],
                    target_was_struck=item['targetWasStruck'])
        comparisons.append({'kind': item['kind'], 'reference': reference['id'], 'changed': changed['id'],
                            'measurement': value})
    tool_hash = hashlib.sha256()
    for source in sorted(Path(__file__).parent.glob('*.py')):
        tool_hash.update(source.name.encode()+b'\0'+source.read_bytes())
    return {'schemaVersion': 1, 'toolSourceSha256': tool_hash.hexdigest(), 'tool': 'moonlight-acoustic-analysis', 'toolVersion': __version__,
            'dependencies': {'python': platform.python_version(), 'numpy': np.__version__,
                             'scipy': scipy.__version__, 'soundfile': sf.__version__,
                             'libsndfile': sf.__libsndfile_version__},
            'evidenceKind': job['evidenceKind'], 'jobSha256': hashlib.sha256(job_bytes).hexdigest(),
            'parameters': {'renderedRateHz': rendered_rate, **asdict(config)},
            'reproduceCommand': command or ['python3', '-m', 'tools.acoustics.cli', '--manifest', str(job_path),
                                          '--rendered-rate', str(rendered_rate)],
            'limitations': [
                'Synthetic validation proves estimator behavior, not professional piano sound quality.',
                'Unknown recording velocity, note-off, pedal, or microphone metadata are not inferred.',
                'Levels are RMS/peak dBFS, not calibrated SPL or BS.1770 integrated LUFS.',
                'Source-native high-rate analysis is available; upsampling cannot recover absent partials.',
                'Phase/delay requires same-take synchronization; measured transfer includes room and microphones.'],
            'cases': results, 'comparisons': comparisons}


def markdown(report):
    lines = ['# Objective acoustic evidence', '',
             f"Tool: `{report['tool']} {report['toolVersion']}`", '',
             f"Evidence kind: **{report['evidenceKind']}**", '',
             f"Prepared-job SHA-256: `{report['jobSha256']}`", '', '## Reproduce', '', '```sh',
             shlex.join(report['reproduceCommand']), '```', '', '## Measurements', '']
    for case in report['cases']:
        m = case['measurement']
        lines += [f"### {case['id']}", '',
                  f"Conditions: `{json.dumps(m['conditions'], sort_keys=True)}`", '',
                  f"Recording SHA-256: `{case['recordingSha256']}`", '',
                  f"Fundamental: {m['fundamental']['hz']} Hz ({m['fundamental']['status']}).",
                  f"Resolved partials: {len(m['partials'])}; common guarded bandwidth: {m['commonGuardedNyquistHz']} Hz.",
                  f"Inharmonicity: `{json.dumps(m['inharmonicity'], sort_keys=True)}`", '',
                  f"Attack: `{json.dumps(m['attack'], sort_keys=True)}`", '',
                  f"Early / late decay: `{json.dumps(m['decay'], sort_keys=True)}`", '',
                  f"Levels (not LUFS): `{json.dumps(m['levels'], sort_keys=True)}`", '',
                  f"Spectral power centroid: {m['spectralCentroidHz']:.3f} Hz.", '',
                  f"Beating: `{json.dumps(m['beating'], sort_keys=True)}`", '',
                  f"Release: `{json.dumps(m['release'], sort_keys=True)}`", '',
                  f"Noise: `{json.dumps(m['noise'], sort_keys=True)}`", '',
                  f"Provenance: `{json.dumps(case['provenance'], sort_keys=True)}`", '',
                  'Full partial tracks and estimator uncertainty are in the companion JSON.', '']
    if report['comparisons']:
        lines += ['## Controlled comparisons', '']
        for item in report['comparisons']:
            # Cross spectra live in JSON; do not flood the human summary.
            value = {key: value for key, value in item['measurement'].items() if key != 'crossSpectrum'}
            lines += [f"### {item['kind']}: {item['reference']} → {item['changed']}", '',
                      f"`{json.dumps(value, sort_keys=True)}`", '']
    lines += ['## Limitations', ''] + ['- '+item for item in report['limitations']]
    return '\n'.join(lines)+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='basename for .json and .md')
    parser.add_argument('--rendered-rate', default=48000, type=int)
    options = parser.parse_args(argv)
    command = ['python3', '-m', 'tools.acoustics.cli', '--manifest', str(options.manifest),
               '--output', str(options.output), '--rendered-rate', str(options.rendered_rate)]
    report = create_report(options.manifest, rendered_rate=options.rendered_rate, command=command)
    serialized = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+'\n'
    options.output.parent.mkdir(parents=True, exist_ok=True)
    Path(str(options.output)+'.json').write_text(serialized)
    Path(str(options.output)+'.md').write_text(markdown(report))
    print(f'wrote {options.output}.json and {options.output}.md')


if __name__ == '__main__':
    main()
