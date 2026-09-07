# Test Server Modpack

A release repository for distributing the complete mod bundle used by the test server.

The latest bundle can always be downloaded from:

https://github.com/najaewon-modding/test-server-modpack/releases/latest/download/test-server-modpack.zip

The bundle is generated automatically from `manifest.json`. To update a mod, change its `version` in the manifest and push the change to `main`. GitHub Actions resolves the matching release JAR, validates the bundle, creates a ZIP, publishes a new GitHub Release, and optionally posts the update to Discord.

## Installation

1. Download `test-server-modpack.zip` from the latest release.
2. Extract the ZIP.
3. Copy every JAR from `required/` into the Minecraft instance's `mods` directory.
4. Optionally copy any JARs you want from `recommended/` into the same `mods` directory.
5. Remove old versions of bundled mods if they are still present in the instance.

`required/` contains the mods expected for the test server. `recommended/` contains optional client-side quality-of-life mods that are useful with the server but are not required to join.

## Updating the bundle

For mods released from repositories under `najaewon-modding`, only the `version` normally needs to be changed. The builder derives:

- tag: `v<version>`
- asset: `<artifact>-<version>.jar`

Each mod also has a `category`:

- `required` — included in the ZIP under `required/`
- `recommended` — included in the ZIP under `recommended/`

Example:

```json
{
  "name": "Compass Bar",
  "category": "required",
  "source": "github_release",
  "repository": "najaewon-modding/compass-bar",
  "artifact": "njw_compass_bar",
  "version": "1.0.3-mc26.1.2"
}
```

A mod can be temporarily excluded by setting `"enabled": false`.

## Automatic release notes

Before publishing a new release, the builder reads the `manifest.json` stored in the latest published modpack release and compares it with the current manifest.

The release notes automatically list:

- added mods
- updated mod versions
- removed mods
- `required` / `recommended` category changes
- modpack version changes

The current `required` and `recommended` lists are also included in every release note.

## Discord announcements

After a GitHub Release is published, the workflow can automatically post a Korean update notice to a Discord channel. The notice contains:

- the modpack version and build number
- added, updated, removed, and recategorized mods
- a link to the latest ZIP
- a short installation reminder

To enable Discord announcements:

1. Create a webhook for the Discord channel that should receive modpack updates.
2. In this repository, open **Settings → Secrets and variables → Actions**.
3. Create a new repository secret named `DISCORD_WEBHOOK_URL`.
4. Paste the Discord webhook URL as the secret value.

If `DISCORD_WEBHOOK_URL` is not configured, releases still work normally and the Discord step is skipped.

## Bundle contents

The current versions and categories are defined exclusively by `manifest.json`. Each generated ZIP contains:

- `required/` — mods required for the test server
- `recommended/` — optional recommended client-side mods
- `MODS.txt` — resolved mod list grouped by category
- `SHA256SUMS.txt` — SHA-256 checksums for every bundled JAR
- `manifest.json` — the exact manifest used to create that bundle
- `THIRD_PARTY_NOTICES.txt` — third-party attribution information

### Required

- Compass Bar
- Just Chat
- Just Dragon Eggs
- Just End Portal
- Just Skills
- Just Tractor
- Librarian Negotiations
- Simple Voice Chat

### Recommended

- Clean Shot
- Just Volume Controller

## Third-party software

The bundle includes **Simple Voice Chat** by Max Henkel. Simple Voice Chat's official FAQ explicitly permits use in modpacks with credit. The build downloads the pinned file from Modrinth and verifies its SHA-256 checksum before packaging it.

Official project: https://modrepo.de/minecraft/voicechat/overview

## Compatibility

- Minecraft 26.1.2
- NeoForge 26.1.2.97

This repository only distributes the test server's mod bundle; individual mods remain subject to their respective licenses.
