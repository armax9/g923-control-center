# Control Center app icon

Original vector artwork: a three-spoke steering wheel with an audio waveform hub, rendered in blue and cyan on a dark navy macOS tile.

The editable source is `scripts/render-control-center-icon.swift`. Regenerate both assets from the project directory:

```sh
swift -module-cache-path /tmp/g923-icon-module-cache scripts/render-control-center-icon.swift
```

`AppIcon.png` is the 1024 px preview. `AppIcon.icns` includes 16, 32, 64, 128, 256, 512, and 1024 px PNG representations; the generator checks that AppKit can decode the container. The control-center packaging script copies it into the app bundle and sets `CFBundleIconFile`.
