#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the WinMM forwarding loader using an explicitly selected Wine export table."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def exports_from(path):
    data = Path(path).read_bytes()
    def u16(offset): return struct.unpack_from('<H', data, offset)[0]
    def u32(offset): return struct.unpack_from('<I', data, offset)[0]
    if data[:2] != b'MZ' or len(data) < 64:
        raise ValueError('Select an x64 Wine winmm.dll')
    try:
        nt = u32(60)
        if data[nt:nt + 4] != b'PE\0\0' or u16(nt + 4) != 0x8664 or u16(nt + 24) != 0x20b:
            raise ValueError('Select an x64 Wine winmm.dll')
        opt = nt + 24
        sections = []
        for index in range(u16(nt + 6)):
            pos = opt + u16(nt + 20) + index * 40
            sections.append((u32(pos + 12), max(u32(pos + 8), u32(pos + 16)), u32(pos + 20)))
        def at(rva):
            for base, length, raw in sections:
                if base <= rva < base + length and raw + rva - base < len(data):
                    return raw + rva - base
            raise ValueError('Invalid WinMM export RVA')
        entry = at(u32(opt + 112))
        base, count, names_count = u32(entry + 16), u32(entry + 20), u32(entry + 24)
        if count > 65536 or names_count > count:
            raise ValueError('Invalid WinMM export count')
        functions, names, ordinals = at(u32(entry + 28)), at(u32(entry + 32)), at(u32(entry + 36))
        by_ordinal = {}
        for index in range(names_count):
            pos = at(u32(names + index * 4))
            name = data[pos:data.index(0, pos)].decode('ascii')
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
                raise ValueError('Unsupported WinMM export name')
            by_ordinal[u16(ordinals + index * 2)] = name
        result = [{'name': by_ordinal.get(index), 'ordinal': base + index} for index in range(count) if u32(functions + index * 4)]
        if not result or not any(item['name'] == 'timeGetTime' for item in result):
            raise ValueError('The selected DLL does not have the Wine WinMM export table')
        return result
    except (IndexError, struct.error, UnicodeError) as error:
        raise ValueError('Invalid WinMM PE export table') from error


def build(original, output, zig):
    exports = exports_from(original)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    assembly, names, definition = ['.text'], [], ['LIBRARY winmm', 'EXPORTS']
    for index, item in enumerate(exports):
        name, ordinal = item['name'], item['ordinal']
        names.append(json.dumps(name) if name else f'((const char*)(unsigned long long){ordinal})')
        definition.append(f'{name}=wp_{index} @{ordinal}' if name else f'wp_{index} @{ordinal} NONAME')
        assembly += ['.p2align 4', f'.globl wp_{index}', f'wp_{index}:', 'pushq %rcx', 'pushq %rdx',
                     'pushq %r8', 'pushq %r9', 'subq $104, %rsp', 'movaps %xmm0,32(%rsp)',
                     'movaps %xmm1,48(%rsp)', 'movaps %xmm2,64(%rsp)', 'movaps %xmm3,80(%rsp)',
                     f'movl ${index},%ecx', 'callq winmm_resolve', 'movaps 32(%rsp),%xmm0',
                     'movaps 48(%rsp),%xmm1', 'movaps 64(%rsp),%xmm2', 'movaps 80(%rsp),%xmm3',
                     'addq $104,%rsp', 'popq %r9', 'popq %r8', 'popq %rdx', 'popq %rcx', 'jmpq *%rax']
    (output / 'forward.S').write_text('\n'.join(assembly) + '\n')
    (output / 'names.c').write_text('const char*winmm_names[]={' + ','.join(names) + '};\n')
    (output / 'exports.def').write_text('\n'.join(definition) + '\n')
    environment = os.environ.copy()
    environment.setdefault('ZIG_GLOBAL_CACHE_DIR', str(output / 'zig-cache'))
    environment.setdefault('ZIG_LOCAL_CACHE_DIR', str(output / 'zig-local'))
    subprocess.run([zig, 'dlltool', '-m', 'i386:x86-64', '-d', str(ROOT / 'vendor/crossover-ffb/Bridge/kernel32.def'),
                    '-l', str(output / 'kernel32.lib')], env=environment, check=True)
    objects = []
    for source in [Path(__file__).parent / 'chain.c', output / 'names.c', output / 'forward.S']:
        obj = output / (source.stem + '.obj')
        objects.append(str(obj))
        subprocess.run([zig, 'cc', '-target', 'x86_64-windows-msvc', '-O2', '-ffreestanding',
                        '-fno-builtin', '-fno-stack-protector', '-c', str(source), '-o', str(obj)],
                       env=environment, check=True)
    payload = output / 'winmm.dll'
    subprocess.run([zig, 'cc', '-target', 'x86_64-windows-msvc', '-nostdlib', '-shared', *objects,
                    str(output / 'kernel32.lib'), str(output / 'exports.def'), '-Wl,--entry,DllMain', '-o', str(payload)],
                   env=environment, check=True)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wine-winmm', type=Path, default=os.environ.get('G923_WINE_WINMM'),
                        help='Original x64 Wine winmm.dll, used only to read exports; or set G923_WINE_WINMM.')
    parser.add_argument('--zig', default=os.environ.get('ZIG'), help='Zig executable; defaults to ZIG or zig on PATH.')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/winmm-chain')
    args = parser.parse_args()
    if not args.wine_winmm:
        parser.error('--wine-winmm or G923_WINE_WINMM must explicitly select the Wine DLL')
    zig = shutil.which(str(args.zig or 'zig'))
    if not zig:
        parser.error('Zig was not found; use --zig, ZIG or PATH')
    print(build(args.wine_winmm.expanduser().resolve(), args.output, zig))


if __name__ == '__main__':
    main()
