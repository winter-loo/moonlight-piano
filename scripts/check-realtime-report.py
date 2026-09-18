"""Validate benchmark evidence and compare only equivalent dedicated runs."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

MATRIX = {(rate, frames) for rate in (44100, 48000) for frames in (64, 128, 256, 512)}
IDENTITY = ('deviceId', 'cpu', 'architecture', 'os', 'compiler', 'kernel', 'scene', 'warmupBlocks')
BUDGETS = {'p50': .25, 'p99': .45, 'p9999': .70}


def validate(report):
    if not isinstance(report, dict) or type(report.get('schemaVersion')) is not int or report.get('schemaVersion') != 1 or report.get('mode') not in ('smoke', 'dedicated'):
        raise ValueError('unsupported report')
    revision = report.get('sourceRevision')
    if not isinstance(revision, str) or not re.fullmatch(
            r'[0-9a-f]{40}(?:\+worktree-patch-sha256:[0-9a-f]{64})?', revision):
        raise ValueError('sourceRevision must identify the measured commit and optional patch')
    for key in IDENTITY[:-1]:
        if not isinstance(report.get(key), str) or not report[key].strip():
            raise ValueError(f'missing {key}')
    for key in ('warmupBlocks', 'binaryBytes', 'modelBytes'):
        if type(report.get(key)) is not int or report[key] <= 0:
            raise ValueError(f'invalid {key}')
    cases = report.get('cases')
    if not isinstance(cases, list) or len(cases) != 8:
        raise ValueError('exactly eight rate/block cases are required')
    if any(not isinstance(case, dict)
           or type(case.get('sampleRateHz')) is not int
           or type(case.get('blockFrames')) is not int for case in cases):
        raise ValueError('invalid rate/block case')
    keys = {(case['sampleRateHz'], case['blockFrames']) for case in cases}
    if keys != MATRIX:
        raise ValueError('matrix incomplete or duplicated')
    for case in cases:
        for key in ('observations', 'stateBytes', 'outputBytes', 'measurementBufferBytes', 'configuredModes'):
            if type(case.get(key)) is not int or case[key] <= 0:
                raise ValueError(f'invalid {key}')
        if case['outputBytes'] != case['blockFrames']*4:
            raise ValueError('output memory mismatch')
        if case['measurementBufferBytes'] != case['observations']*8:
            raise ValueError('measurement memory mismatch')
        ratios = [case.get(key) for key in ('p50', 'p99', 'p9999', 'max')]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in ratios):
            raise ValueError('invalid ratio')
        if ratios != sorted(ratios):
            raise ValueError('unordered percentile observations')
        if type(case.get('deadlineMisses')) is not int or not 0 <= case['deadlineMisses'] <= case['observations']:
            raise ValueError('invalid deadline count')
        if (case['max'] >= 1.0) != (case['deadlineMisses'] > 0):
            raise ValueError('deadline count contradicts maximum ratio')
        if type(case.get('activeModesPeak')) is not int or not 0 < case['activeModesPeak'] <= case['configuredModes']:
            raise ValueError('benchmark did not exercise active state')
        if report['mode'] == 'dedicated' and case['observations'] < 100000:
            raise ValueError('insufficient tail observations for dedicated run')
    return report


def enforce_budget(report):
    for row in report['cases']:
        if row['deadlineMisses'] or row['max'] >= 1.0 or any(
                row[key] > budget for key, budget in BUDGETS.items()):
            raise ValueError('absolute realtime contract failed; benefit report cannot waive it')


def compare(candidate, baseline):
    validate(candidate)
    validate(baseline)
    if candidate['mode'] != 'dedicated' or baseline['mode'] != 'dedicated':
        raise ValueError('hosted smoke observations are not release baselines')
    if any(candidate[key] != baseline[key] for key in IDENTITY):
        raise ValueError('hardware/toolchain/scene changed; baselines are incomparable')
    enforce_budget(candidate)
    old = {(row['sampleRateHz'], row['blockFrames']): row for row in baseline['cases']}
    changes = []
    for row in candidate['cases']:
        previous = old[(row['sampleRateHz'], row['blockFrames'])]
        if row['observations'] != previous['observations']:
            raise ValueError('observation counts differ')
        for key in ('p50', 'p99', 'p9999', 'stateBytes', 'outputBytes'):
            if row[key] > previous[key] * 1.10:
                changes.append({'rate': row['sampleRateHz'], 'frames': row['blockFrames'],
                                'metric': key, 'before': previous[key], 'after': row[key]})
    for key in ('binaryBytes', 'modelBytes'):
        if candidate[key] > baseline[key]*1.10:
            changes.append({'metric': key, 'before': baseline[key], 'after': candidate[key]})
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--change-report', type=Path)
    parser.add_argument('--enforce-budget', action='store_true',
                        help='also check absolute budgets without a comparison baseline')
    options = parser.parse_args()
    if options.change_report and not options.baseline:
        raise ValueError('--change-report requires --baseline')
    candidate_bytes = options.candidate.read_bytes()
    candidate = validate(json.loads(candidate_bytes))
    budget_checked = options.enforce_budget or candidate['mode'] == 'dedicated' or bool(options.baseline)
    if budget_checked:
        enforce_budget(candidate)
    changes = None
    if options.baseline:
        baseline_bytes = options.baseline.read_bytes()
        changes = compare(candidate, json.loads(baseline_bytes))
        if changes:
            if not options.change_report:
                raise ValueError('regression requires acoustic-benefit/error-metric report: ' + json.dumps(changes))
            justification = json.loads(options.change_report.read_text())
            for key, data in (('baselineSha256', baseline_bytes), ('candidateSha256', candidate_bytes)):
                if justification.get(key) != hashlib.sha256(data).hexdigest():
                    raise ValueError('change report is not bound to the measured evidence')
            if not justification.get('acousticBenefit') or not justification.get('reviewReference'):
                raise ValueError('acousticBenefit and reviewReference are required')
            errors = justification.get('errorMetrics')
            if not isinstance(errors, list) or not errors:
                raise ValueError('changed acoustic error measurements are required')
            for error in errors:
                if not error.get('name') or not error.get('unit'):
                    raise ValueError('name/unit required for each error metric')
                if any(type(error.get(key)) not in (float, int) or not math.isfinite(error[key])
                       for key in ('before', 'after')):
                    raise ValueError('error metrics must be finite measured values')
    print(json.dumps({'validated': True, 'mode': candidate['mode'], 'regressions': changes,
                      'dedicatedComparison': bool(options.baseline),
                      'absoluteBudgetChecked': budget_checked,
                      'thermalCertification': False}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error)) from error
