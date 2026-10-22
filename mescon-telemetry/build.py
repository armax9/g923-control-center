#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the standalone GPL-2.0 components; no game, sockets or hardware."""
import argparse,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--rustc',type=Path,required=True);p.add_argument('--mingw',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parent;out=root/'build';out.mkdir(exist_ok=True)
for source,name in [('synth.rs','synth-tests'),('scs_plugin.rs','plugin-tests'),('main.rs','adapter-tests'),('windows-relay/main.rs','relay-tests')]:
 binary=out/name;subprocess.run([str(a.rustc.resolve()),'--edition=2021','--test',str(root/'src'/source),'-o',str(binary)],check=True);subprocess.run([str(binary)],check=True)
subprocess.run([str(a.rustc.resolve()),'--edition=2021','-C','opt-level=2',str(root/'src/main.rs'),'-o',str(out/'mescon-synth')],check=True)
subprocess.run([str(a.rustc.resolve()),'--edition=2021','--crate-type','cdylib','--crate-name','logi_tf_scs','--target','x86_64-pc-windows-gnullvm','-C','opt-level=2','-C','target-feature=+crt-static','-C','link-arg=-static','-C','linker='+str(a.mingw.resolve()),str(root/'src/scs_plugin.rs'),'-o',str(out/'logi_tf_scs.dll')],check=True)

subprocess.run([str(a.rustc.resolve()),'--edition=2021','--target','x86_64-pc-windows-gnullvm','-C','opt-level=2','-C','target-feature=+crt-static','-C','link-arg=-static','-C','linker='+str(a.mingw.resolve()),str(root/'src/windows-relay/main.rs'),'-o',str(out/'logi-tf-relay.exe')],check=True)
