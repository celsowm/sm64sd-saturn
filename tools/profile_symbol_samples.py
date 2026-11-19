#!/usr/bin/env python3
"""Summarize a probe --profile-pc sample file by matching ELF symbol.

The probe samples once per emulated field; these counts are statistical and
include startup. They are not cycle or instruction counts.
"""
import argparse
import bisect
from collections import Counter
import json
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--samples', required=True, type=Path)
    parser.add_argument('--nm', type=Path, default=root.parent/'saturn-tools/bin/sh2eb-elf-nm')
    parser.add_argument('--limit', type=int, default=25)
    args = parser.parse_args()
    table = []
    for line in subprocess.check_output([str(args.nm), '-n', '-S', str(args.elf)], text=True).splitlines():
        fields = line.split()
        if len(fields) != 4 or fields[2].lower() != 't':
            continue
        try:
            address, size = int(fields[0], 16), int(fields[1], 16)
        except ValueError:
            continue
        if size:
            table.append((address, address+size, fields[3]))
    table.sort()
    starts = [row[0] for row in table]
    counts = Counter()
    for line in args.samples.read_text().splitlines():
        try:
            pc = int(line.strip(), 16)
        except ValueError as exc:
            raise ValueError(f'invalid sample: {line!r}') from exc
        index = bisect.bisect_right(starts, pc)-1
        name = table[index][2] if index >= 0 and pc < table[index][1] else '<unmapped>'
        counts[name] += 1
    print(json.dumps({'total_samples': sum(counts.values()),
                      'symbols': [{'name': name, 'samples': count}
                                  for name, count in counts.most_common(args.limit)]}, indent=2))


if __name__ == '__main__':
    main()
