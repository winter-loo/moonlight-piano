"""Fail closed on a missing renderer or unreviewed object-level dependencies."""
import argparse
from pathlib import Path


def check(defined, undefined):
    retained = any(
        len(fields := line.split()) >= 3 and fields[1] == 'T'
        and 'RealtimeState' in line and 'process_block' in line
        for line in defined.splitlines()
    )
    if not retained:
        raise ValueError('production render symbol missing; refusing an empty-object audit')
    allowed = {'memset', 'memcpy', 'memmove'}
    for line in undefined.splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) == 1:  # BSD nm may emit just the undefined symbol.
            symbol = fields[0]
        elif len(fields) == 2 and fields[0] == 'U':
            symbol = fields[1]
        else:
            raise ValueError(f'unrecognized undefined-symbol record: {line}')
        # Mach-O C symbols have one leading underscore. Never strip arbitrary
        # prefixes, or an unrelated runtime helper could enter the allow-list.
        if symbol not in allowed and not (symbol.startswith('_') and symbol[1:] in allowed):
            raise ValueError(f'unreviewed realtime external symbol: {symbol}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('defined', type=Path)
    parser.add_argument('undefined', type=Path)
    args = parser.parse_args()
    check(args.defined.read_text(), args.undefined.read_text())
    print('Production render retained; object dependencies satisfy the reviewed policy')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
