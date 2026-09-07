# Test Server Modpack

A release repository for distributing the complete mod bundle used by the test server.

The latest bundle can always be downloaded from:

https://github.com/najaewon-modding/test-server-modpack/releases/latest/download/test-server-modpack.zip

The bundle is generated automatically from `manifest.json`. To update a mod, change its `version` in the manifest and push the change to `main`. GitHub Actions resolves the matching release JAR, validates the bundle, creates a ZIP, and publishes a new GitHub Release.

## Installation

1. Download `test-server-modpack.zip` from the latest release.
2. Extract it into the Minecraft instance directory.
3. Allow the included `mods` directory to merge with the existing `mods` directory.
4. Remove old versions of bundled mods if they are still present in the instance.

## Updating the bundle

For mods released from repositories under `najaewon-modding`, only the `version` normally needs to be changed. The builder derives:

- tag: `v<version>`
- asset: `<artifact>-<version>.jar`

Example:

```json
{
  "name": "Compass Bar",
  "source": "github_release",
  "repository": "najaewon-modding/compass-bar",
  "artifact": "njw_compass_bar",
  "version": "1.0.3-mc26.1.2"
}
```

A mod can be temporarily excluded by setting `"enabled": false`.

## Bundle contents

The current versions are defined exclusively by `manifest.json`. Each generated ZIP also contains:

- `mods/` — the installable JAR files
- `MODS.txt` — resolved mod list
- `SHA256SUMS.txt` — SHA-256 checksums for every bundled JAR
- `manifest.json` — the exact manifest used to create that bundle
- `THIRD_PARTY_NOTICES.txt` — third-party attribution information

## Third-party software

The bundle includes **Simple Voice Chat** by Max Henkel. Simple Voice Chat's official FAQ explicitly permits use in modpacks with credit. The build downloads the pinned file from Modrinth and verifies its SHA-256 checksum before packaging it.

Official project: https://modrepo.de/minecraft/voicechat/overview

## Compatibility

- Minecraft 26.1.2
- NeoForge 26.1.2.97

This repository only distributes the test server's mod bundle; individual mods remain subject to their respective licenses.
