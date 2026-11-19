#!/usr/bin/env python3
"""Transfer generated-face bake priorities after changing subdivision.

Unchanged source-face groups keep their per-fragment order. Where the number
of fragments changes, each new fragment gets that source's mean priority.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def remap(old_origins, new_origins, priorities):
    if len(old_origins) != len(priorities):
        raise ValueError('old origins and priorities must have equal lengths')
    values = defaultdict(list)
    for origin, priority in zip(old_origins, priorities):
        values[origin].append(priority)
    if set(new_origins) != set(old_origins):
        raise ValueError('old and new origins must contain the same source faces')
    counts = Counter(new_origins)
    seen = Counter()
    result = []
    for origin in new_origins:
        group = values[origin]
        result.append(group[seen[origin]] if len(group) == counts[origin]
                      else sum(group) / len(group))
        seen[origin] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('old-origins', 'new-origins', 'priorities', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    old, new, priorities = (json.loads(p.read_text()) for p in
                            (args.old_origins, args.new_origins, args.priorities))
    args.output.write_text(json.dumps(remap(old, new, priorities)) + '\n')


if __name__ == '__main__':
    main()
