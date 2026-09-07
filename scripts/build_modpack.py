#!/usr/bin/env python3

import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifest.json"
BUILD_DIR = ROOT / "build"
PACKAGE_DIR = BUILD_DIR / "package"
MODS_DIR = PACKAGE_DIR / "mods"
ZIP_PATH = BUILD_DIR / "test-server-modpack.zip"
USER_AGENT = "najaewon-modding/test-server-modpack"


def request_json(url, github=False):
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if github and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} while requesting {url}: {body}") from exc


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} while downloading {url}: {body}") from exc


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def github_release(mod):
    version = required(mod, "version")
    repository = required(mod, "repository")
    artifact = required(mod, "artifact")
    tag = mod.get("tag", f"v{version}")
    asset_name = mod.get("asset", f"{artifact}-{version}.jar")
    url = f"https://api.github.com/repos/{repository}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    release = request_json(url, github=True)
    matches = [asset for asset in release.get("assets", []) if asset.get("name") == asset_name]
    if len(matches) != 1:
        available = ", ".join(asset.get("name", "<unnamed>") for asset in release.get("assets", [])) or "none"
        raise RuntimeError(f"{mod['name']}: expected exactly one release asset named {asset_name!r} at {repository}@{tag}; available: {available}")
    return asset_name, matches[0]["browser_download_url"]


def modrinth_release(mod):
    version_id = required(mod, "version_id")
    asset_name = required(mod, "asset")
    version = request_json(f"https://api.modrinth.com/v2/version/{urllib.parse.quote(version_id, safe='')}")
    expected_project = mod.get("project_id")
    if expected_project and version.get("project_id") != expected_project:
        raise RuntimeError(f"{mod['name']}: Modrinth version {version_id} belongs to project {version.get('project_id')}, expected {expected_project}")
    matches = [file for file in version.get("files", []) if file.get("filename") == asset_name]
    if len(matches) != 1:
        available = ", ".join(file.get("filename", "<unnamed>") for file in version.get("files", [])) or "none"
        raise RuntimeError(f"{mod['name']}: expected exactly one Modrinth file named {asset_name!r}; available: {available}")
    return asset_name, matches[0]["url"]


def required(mapping, key):
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Missing or invalid {key!r} in manifest entry: {mapping}")
    return value


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pack"), dict) or not isinstance(manifest.get("mods"), list):
        raise RuntimeError("manifest.json must contain a 'pack' object and a 'mods' array")
    for key in ("name", "version", "minecraft", "neoforge"):
        required(manifest["pack"], key)
    enabled = [mod for mod in manifest["mods"] if mod.get("enabled", True)]
    if not enabled:
        raise RuntimeError("At least one mod must be enabled")
    names = [required(mod, "name") for mod in enabled]
    if len(names) != len(set(names)):
        raise RuntimeError("Enabled mod names must be unique")


def write_metadata(manifest, resolved):
    pack = manifest["pack"]
    mods_lines = [
        f"{pack['name']} {pack['version']}",
        f"Minecraft {pack['minecraft']}",
        f"NeoForge {pack['neoforge']}",
        "",
        "Bundled mods:",
    ]
    for item in resolved:
        mods_lines.append(f"- {item['name']} {item['version']} ({item['filename']})")
    (PACKAGE_DIR / "MODS.txt").write_text("\n".join(mods_lines) + "\n", encoding="utf-8")

    checksum_lines = [f"{item['sha256']}  mods/{item['filename']}" for item in resolved]
    (PACKAGE_DIR / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    notices = []
    for mod, item in zip([m for m in manifest["mods"] if m.get("enabled", True)], resolved):
        if mod.get("third_party"):
            notices.extend([
                f"{item['name']} {item['version']}",
                f"Author: {mod.get('author', 'Unknown')}",
                f"Homepage: {mod.get('homepage', 'Not specified')}",
                "Included as part of this test-server modpack; all rights remain with the original author.",
                "",
            ])
    if not notices:
        notices.append("No third-party notices are currently required.\n")
    (PACKAGE_DIR / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(notices).rstrip() + "\n", encoding="utf-8")
    shutil.copy2(MANIFEST_PATH, PACKAGE_DIR / "manifest.json")

    notes = [
        f"# {pack['name']} {pack['version']}",
        "",
        f"Automated test-server bundle for Minecraft **{pack['minecraft']}** and NeoForge **{pack['neoforge']}**.",
        "",
        "## Included mods",
        "",
    ]
    notes.extend(f"- **{item['name']}** {item['version']}" for item in resolved)
    notes.extend([
        "",
        "## Installation",
        "",
        "1. Download `test-server-modpack.zip` from the Assets section.",
        "2. Extract it into your Minecraft instance directory.",
        "3. Merge the included `mods` directory with your existing `mods` directory.",
        "4. Remove older versions of the bundled mods if they are still present.",
        "",
        "The ZIP includes the exact manifest and SHA-256 checksums used for this build.",
    ])
    third_party = [m for m in manifest["mods"] if m.get("enabled", True) and m.get("third_party")]
    if third_party:
        notes.extend(["", "## Third-party credits", ""])
        for mod in third_party:
            notes.append(f"- **{mod['name']}** by {mod.get('author', 'Unknown')} — {mod.get('homepage', '')}")
    (BUILD_DIR / "release-notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")


def create_zip():
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(PACKAGE_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(PACKAGE_DIR).as_posix())


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    MODS_DIR.mkdir(parents=True)

    resolved = []
    seen_files = set()
    for mod in manifest["mods"]:
        if not mod.get("enabled", True):
            continue
        source = required(mod, "source")
        if source == "github_release":
            filename, url = github_release(mod)
        elif source == "modrinth":
            filename, url = modrinth_release(mod)
        else:
            raise RuntimeError(f"{mod['name']}: unsupported source {source!r}")
        if not filename.lower().endswith(".jar"):
            raise RuntimeError(f"{mod['name']}: resolved asset is not a JAR: {filename}")
        if filename in seen_files:
            raise RuntimeError(f"Duplicate output filename: {filename}")
        seen_files.add(filename)
        destination = MODS_DIR / filename
        print(f"Downloading {mod['name']} {mod['version']} -> {filename}")
        download(url, destination)
        actual_hash = sha256(destination)
        expected_hash = mod.get("sha256")
        if expected_hash and actual_hash.lower() != expected_hash.lower():
            raise RuntimeError(f"{mod['name']}: SHA-256 mismatch for {filename}: expected {expected_hash}, got {actual_hash}")
        resolved.append({"name": mod["name"], "version": required(mod, "version"), "filename": filename, "sha256": actual_hash})

    write_metadata(manifest, resolved)
    create_zip()
    print(f"Built {ZIP_PATH.relative_to(ROOT)} with {len(resolved)} mods")
    for item in resolved:
        print(f"  {item['sha256']}  {item['filename']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
