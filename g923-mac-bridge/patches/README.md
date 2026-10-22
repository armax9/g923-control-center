# G923 Wine TRUEFORCE transport

These patches expose the Logitech G923 PlayStation TRUEFORCE HID collection to the original Logitech SDK under Wine on macOS. They do not synthesize effects or implement the proprietary SDK.

The accepted pair targets **CrossOver Preview 27.0.0.41069**, build `20261006T113703Z`, with upstream **Wine 11.17**, commit `36b6a2cf679fb395f668a917b76537190e212d9c`. See [the catalog](transport-catalog.json) for original and replacement module hashes. A shared version label alone does not prove ABI compatibility.

The implementation changes only `dlls/winebus.sys/bus_iohid.c` and `dlls/winebus.sys/main.c`:

- Admit vendor collection `FFFD:FD01` only for Logitech `046d:c266/c267`.
- Supply the USB interface/class metadata expected by the SDK.
- Give HID interfaces at one USB location the same Windows device container.

`winebus-11.17-g923-trueforce.patch` is the exact functional patch used for the accepted pair. `winebus-11.17-g923-change-notices.patch` adds dated modification notices to the two source files. Its comments do not change the transport logic. The older `winebus-g923-trueforce-vendor-collection.patch` records the preliminary experiment; it is not the complete accepted fix.

The USB metadata helpers were adapted from upstream Wine commit [`840a939ee526137639665ff5f587224d6a36403f`](https://github.com/wine-mirror/wine/blob/840a939ee526137639665ff5f587224d6a36403f/dlls/winebus.sys/bus_iohid.c). They retain Wine's LGPL-2.1-or-later licensing. The transport changes are provided under the same terms. Original copyright notices are retained.

Modified Wine modules are distributed with the complete corresponding Wine source, patches, build script, notices and [Wine's LGPL text](https://raw.githubusercontent.com/wine-mirror/wine/wine-11.17/COPYING.LIB). [LGPL 2.1 section 4](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html#SEC3) explains the source requirement for library binaries. The project does not distribute Logitech SDK DLLs or a commercial CrossOver runtime.

[Build and source-package instructions](../docs/WINE_TRANSPORT_SOURCE.md) include the update process for future Wine versions.
