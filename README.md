# Test Server Modpack

A release repository for distributing the complete mod bundle used by the test server.

The latest published bundle can always be downloaded from:

https://github.com/najaewon-modding/test-server-modpack/releases/latest/download/test-server-modpack.zip

## What to edit

Normal operation only requires changes to `manifest.json`.

For a normal modpack update:

1. Add, remove, enable, disable, or recategorize a mod, or change a mod's `version` / pinned download target.
2. Push the manifest change to `main`.
3. Let the push-triggered workflow build and validate the pending configuration.
4. When the configuration is ready to publish, manually run `Build and Release Modpack` from GitHub Actions.
5. Do not change `pack.version` unless you intentionally want to jump to a higher version such as `1.1.0` or `2.0.0`.

A normal push never publishes a GitHub Release and never sends a Discord announcement. Publishing is reserved for manual workflow runs.

## Categories

The bundle supports three mod categories:

- `required` — client mods required to join the test server
- `recommended` — optional recommended client-side mods
- `server` — server-only mods; do not copy these into the client `mods` folder

## Automatic versioning

The workflow compares the current distributable configuration with the latest published modpack release.

A distributable configuration change includes:

- Minecraft version changes
- NeoForge version changes
- adding or removing an enabled mod
- enabling or disabling a mod
- `required` / `recommended` / `server` category changes
- mod version changes
- changes to the source information that determines the downloaded JAR, such as repository/tag/asset or Modrinth version ID
- pinned SHA-256 changes

If the distributable configuration changed and `pack.version` was not manually set to a higher version, the latest released version is automatically patch-bumped when the builder runs:

```text
1.0.0 -> 1.0.1 -> 1.0.2
```

If you intentionally set `pack.version` to a version higher than the latest release in the same manifest update, that version is used instead:

```text
latest release: 1.0.7
manifest pack.version: 1.1.0
result: 1.1.0
```

An explicit `pack.version` increase without a distributable configuration change is rejected.

Automatic patch bumps are derived from the latest release and do not rewrite `manifest.json` on `main`. Therefore the `pack.version` stored in the repository may be lower than the next effective version calculated during validation. That is expected; only edit it when you want to force a higher version such as `1.1.0` or `2.0.0`.

## Validation and release

For every workflow run, the builder:

- validates the manifest structure and semantic version format
- validates the `required`, `recommended`, and `server` categories
- resolves every enabled mod from its pinned GitHub Release or Modrinth version
- requires exactly one matching JAR
- validates pinned SHA-256 values when provided
- prevents duplicate output filenames
- generates the exact bundled `manifest.json`
- generates `MODS.txt`, `SHA256SUMS.txt`, and `THIRD_PARTY_NOTICES.txt`
- includes `설치 가이드.html`
- creates `test-server-modpack.zip`
- generates release notes and the Discord payload

Push-triggered runs stop after build and validation. Only a manually started `workflow_dispatch` run publishes or updates a GitHub Release.

## Discord announcements

Discord announcements are only considered during a manual release run, and are sent only when the distributable modpack configuration differs from the latest published release.

The announcement contains:

- the new modpack version
- automatically generated change details
- the latest ZIP download link
- `압축 파일에 있는 설치 가이드를 참고해주세요`

The public Discord title does not include the internal GitHub Actions build number.

The webhook URL must be stored as the repository Actions secret `DISCORD_WEBHOOK_URL`. If the secret is missing, the release still succeeds and only the Discord step is skipped.

## Manifest conventions

For mods released from repositories under `najaewon-modding`, only the mod's `version` normally needs to be changed. Unless explicitly overridden, the builder derives:

- tag: `v<version>`
- asset: `<artifact>-<version>.jar`

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

Third-party mods can use exact external pins such as a Modrinth `version_id`, asset filename, and SHA-256.

## Bundle contents

Each generated ZIP contains:

- `required/` — client mods required for the test server
- `recommended/` — optional recommended client-side mods
- `server/` — server-only mods
- `설치 가이드.html` — Korean NeoForge and test-server installation guide
- `MODS.txt` — resolved mod list grouped by category
- `SHA256SUMS.txt` — SHA-256 checksums for every bundled JAR
- `manifest.json` — exact manifest for that build, including the effective automatically calculated modpack version
- `THIRD_PARTY_NOTICES.txt` — third-party attribution information

## Third-party software

The bundle includes **Simple Voice Chat** by Max Henkel. Simple Voice Chat's official FAQ explicitly permits use in modpacks with credit. The build downloads the pinned file from Modrinth and verifies its SHA-256 checksum before packaging it.

Official project: https://modrepo.de/minecraft/voicechat/overview

## Compatibility

- Minecraft 26.1.2
- NeoForge 26.1.2.97

This repository only distributes the test server's mod bundle; individual mods remain subject to their respective licenses.
