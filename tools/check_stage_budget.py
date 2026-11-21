#!/usr/bin/env python3
"""Fail when a stage ELF leaves too little High or Low WRAM free.

High WRAM is 0x06000000-0x060FFFFF (the loader sits at its start),
Low WRAM 0x00200000-0x002FFFFF. Sizes come from `nm`/`size -A`.
"""
import argparse
from pathlib import Path
import subprocess
import sys

HWRAM_END, LWRAM_BASE, LWRAM_END = 0x06100000, 0x00200000, 0x00300000


def measure(elf, nm, size):
    syms = {}
    for line in subprocess.check_output([nm, '-n', str(elf)], text=True).splitlines():
        w = line.split()
        if len(w) == 3:
            syms[w[2].lstrip('_')] = int(w[0], 16)
    lwram = 0
    for line in subprocess.check_output([size, '-A', str(elf)], text=True).splitlines():
        w = line.split()
        if len(w) == 3 and w[0] == '.wram_l':
            lwram = int(w[1])
    return HWRAM_END - syms['bss_end'], (LWRAM_END - LWRAM_BASE) - lwram


def main():
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--min-free-hwram', type=int, default=32768)
    p.add_argument('--min-free-lwram', type=int, default=0)
    p.add_argument('--nm', default=str(root.parent / 'saturn-tools/bin/sh2eb-elf-nm'))
    p.add_argument('--size', default=str(root.parent / 'saturn-tools/bin/sh2eb-elf-size'))
    a = p.parse_args()
    hw, lw = measure(a.elf, a.nm, a.size)
    print(f'{a.elf.name}: free High WRAM {hw} B, free Low WRAM {lw} B')
    if hw < a.min_free_hwram or lw < a.min_free_lwram:
        print('stage over WRAM budget', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
