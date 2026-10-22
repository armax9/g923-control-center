# Process-local admission experiment

`hid_admission.c` is a diagnostic experiment, not the supported bridge or a TRUEFORCE implementation. It changes only two IOHID properties for G923 FFFD:FD01 inside the process, retaining the original report descriptor. It intercepts synchronous SetReport for the wheel; **do not treat this as a universal output firewall** (other APIs are not covered).

Build on macOS:

```sh
clang -dynamiclib -arch x86_64 -arch arm64 -Wall -Wextra -Werror \
 src/experimental/hid_admission.c -framework IOKit -framework CoreFoundation \
 -o build/g923-hid-admission.dylib
```

20 October result: constructor and admission logging confirmed with our native `g923-hid`. In the lab CrossOver launch via `--env DYLD_INSERT_LIBRARIES=...`, no constructor/admission log appeared and Windows still had only the joystick collection. Thus injection into the relevant Wine process was **not verified**, the mechanism did not expose TRUEFORCE, and the deny hook cannot be assumed active there. The precise cause of the missing load was not established. No security settings, signatures or installed CrossOver files were changed. Do not disable SIP/AMFI or re-sign CrossOver to use this experiment.

The source-level alternative is the proposal in `patches/winebus-g923-trueforce-vendor-collection.patch`. It requires an isolated Wine build and a new read-only inventory proving FFFD:FD01 before any SDK haptic test. The native input bridge does not use this experiment.
