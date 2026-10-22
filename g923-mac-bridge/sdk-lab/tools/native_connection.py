# SPDX-License-Identifier: GPL-3.0-only
"""Read-only checks of the transport actually loaded by this bottle's Wine bus."""
from pathlib import Path
import subprocess

from portable_paths import digest


def assess(prefix, expected, processes, open_paths, hash_file=digest):
    """Pure fixture-friendly check; unrelated bottles do not establish readiness."""
    prefix=Path(prefix).resolve()
    observations=[]
    for pid,command in processes:
        name=command.strip().replace('\\','/').rsplit('/',1)[-1].casefold()
        if name!='winedevice.exe':continue
        paths=[Path(p) for p in open_paths(pid) if p.startswith('/')]
        if not any(p==prefix or prefix in p.parents for p in paths):continue
        modules={}
        for path in paths:
            relative='x86_64-unix/winebus.so' if path.name=='winebus.so' else 'x86_64-windows/winebus.sys' if path.name=='winebus.sys' else None
            if relative:
                try:modules[relative]=hash_file(path)
                except OSError:return {'state':'unknown','detail':'The loaded TRUEFORCE transport could not be inspected.'}
        if modules:observations.append(modules)
    if not observations:
        return {'state':'waiting','detail':'Waiting for this bottle to load the TRUEFORCE transport.'}
    if any(any(modules.get(key)!=value for key,value in expected.items()) for modules in observations):
        return {'state':'restart_required','detail':'Restart Steam and this bottle to load the installed TRUEFORCE transport.'}
    return {'state':'ready','detail':'The reviewed TRUEFORCE transport is loaded. Game SDK connection is checked separately.'}


def live_status(session, manifest):
    from native_transport import check_config
    configuration=check_config(session,manifest)
    if not configuration['configured']:
        return {'state':'setup_required','detail':configuration['detail']}
    try:
        text=subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True,timeout=4)
        processes=[]
        for line in text.splitlines():
            fields=line.strip().split(None,1)
            if len(fields)==2 and fields[0].isdecimal():processes.append((int(fields[0]),fields[1]))
        def paths(pid):
            result=subprocess.run(['/usr/sbin/lsof','-n','-P','-p',str(pid),'-Fn'],capture_output=True,text=True,timeout=4)
            if result.returncode not in (0,1):raise OSError('Cannot inspect Wine modules')
            return [line[1:] for line in result.stdout.splitlines() if line.startswith('n')]
        return assess(manifest['source_bottle'],manifest['runtime_hashes'],processes,paths)
    except (OSError,ValueError,subprocess.SubprocessError):
        return {'state':'unknown','detail':'The loaded TRUEFORCE transport has not been verified.'}
