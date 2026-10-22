# Native TRUEFORCE setup

Native TRUEFORCE uses the game's original Logitech signal. It needs both the
Windows Logitech TRUEFORCE SDK and the compatible G923 Wine transport. Engine
vibration generated from telemetry, such as the ETS2 integration, is a separate
emulated mode.

## Get the Logitech SDK

1. Open [Logitech G HUB](https://www.logitechg.com/en-us/software/ghub) in Windows
   and choose the Windows download. Install G HUB in Windows, including Windows
   in Parallels. The macOS G HUB download does not provide this Windows DLL.
2. In Windows File Explorer, open
   `C:\Program Files\Logi\Trueforce\1_3_12`.
3. Copy `trueforce_sdk_x64.dll` to a shared folder that Finder can access, for
   example the Mac Downloads folder through Parallels sharing. Keep its original
   filename. The wheel does not need to be assigned to Windows for this copy.
4. In G923 Control Center, open the game's **Native TRUEFORCE setup** card, select
   **Import SDK…**, and choose the copied DLL.

The app stores the verified file at:

```
~/Library/Application Support/G923 Control Center/SDK/1_3_12/trueforce_sdk_x64.dll
```

This release accepts the original **1.3.12 x64** DLL with SHA-256:

```
2468bdafe64c09ff42ef26f09e49f2096321bb687467323aafb3f0672fb83315
```

The importer checks its bytes and Windows PE architecture without running the
DLL. A changed file, the x86 DLL or a newer unvalidated SDK is rejected. G HUB
versions can ship different SDK versions; a successful G HUB installation does
not guarantee that this supported DLL is present. If `1_3_12` is absent, use your
own existing G HUB installation or backup containing the supported version.
The public Steering Wheel SDK download is a different SDK.

The recorded Windows source path, version and digest are in
[SDK provenance](SDK_RUNTIME_PROVENANCE.json). That record comes from the G HUB
installation used for the accepted G923 PlayStation tests; it is not a claim
about the contents of every current G HUB installer. Logitech's DLL is not
included in this project or its downloads.

## Install the Wine transport

1. Quit the game and exit Steam completely before installing its integration.
   Open G923 Control Center to perform setup.
2. Open the game's **Native TRUEFORCE setup** card. Its detected CrossOver or
   CrossOver Preview bottle is shown on the game page.
3. Use **Install transport**. Setup verifies that the transport matches the
   selected CrossOver build before preparing a private runtime. If a matching
   build is unavailable, the app reports that requirement rather than installing
   an incompatible driver.
4. Use **Install game integration** on that page. This enables the transport for
   the selected bottle. Setup puts
   the imported DLL in the selected bottle at
   `C:\Program Files\Logi\Trueforce\1_3_12\trueforce_sdk_x64.dll` and configures
   its SDK registration. The file remains under your account.
5. The bridge starts with the app. Open your normal Steam and launch the game yourself.
   You choose desktop or VR mode in Steam.

An imported SDK, installed transport and running game connection are separate
statuses. Installing the DLL alone does not make a stock Wine transport support
the G923 SDK. After changing transport, a full Steam restart is required so Wine
loads the selected modules.

For DiRT Rally 2.0, open the G923 **Vibration & Feedback** page and scroll to
**Enable TRUEFORCE**, **Logitech TRUEFORCE Engine**, **Surface** and **Tyre Slip**.
These are the native TRUEFORCE controls. The separate generic **Engine** and
**Tyre Slip** entries can remain grey. Keep the accepted game settings when
repairing setup.

## Updates and repair

The app checks the installed transport files and their activation for the
selected bottle. A CrossOver update can require a newly built matching
transport. Keep the accepted runtime until the replacement is validated;
matching a folder name or having SDK files installed is insufficient.

Existing SDKs and unrelated mods are preserved. If a destination has changed,
setup reports the conflict and stops. Native game support still requires a
game-specific integration; SDK availability does not turn every game into a
native TRUEFORCE title.

**Wine source & build guide** on the setup card opens the transport source
material. The [source guide](WINE_TRANSPORT_SOURCE.md) records the pinned Wine
revision, G923 changes, both module builds and complete corresponding-source
packaging. A newer Wine or CrossOver build needs a new validated compatibility
entry.
