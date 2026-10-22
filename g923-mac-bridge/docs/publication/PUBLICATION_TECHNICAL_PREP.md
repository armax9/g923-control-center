# Publication checks

This release is a source preview. Gameplay acceptance covers G923 PlayStation / PC with DiRT Rally 2.0 and ETS2 on the setup recorded in the [README](../../README.md).

## Source package

Include project sources, tests, public guides, patches, licenses and the separate `mescon-telemetry` source tree with its GPL-2.0-only notices. Keep its separate-process boundary. Preserve upstream provenance in `NOTICE.md`, `docs/upstream-lock.json` and each component's license.

Include the complete corresponding Wine source archive with any distributed patched Wine modules. Keep the source and binary assets in the same release. See the [Wine source guide](../WINE_TRANSPORT_SOURCE.md).

Exclude original Logitech SDK and CrossOver binaries, games, bottles, profiles, registry backups, captures, personal controls, logs, cached toolchains and development work directories. Scan staged content and Git history; ignore rules alone do not remove previously committed data. Torqer source and assets are not part of this project.

## Before upload

1. Build and test the staged source, including its separate synthesis component.
2. Check relative documentation links, archive contents, licenses and component hashes.
3. Scan source and binary strings for personal paths and identifiers. The current accepted local Wine binaries retain debug build paths; strip or path-map them, then validate their new hashes before public binary distribution.
4. Attach release notes with the exact tested setup. Keep additional games marked untested/pending and clean installation on a second Mac marked pending.
5. Upload only the reviewed source and release assets.

No external publication is implied by preparing these files.
