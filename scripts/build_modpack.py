#!/usr/bin/env python3

import base64
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifest.json"
GUIDE_PATH = ROOT / "docs" / "install-guide.html"
BUILD_DIR = ROOT / "build"
PACKAGE_DIR = BUILD_DIR / "package"
ZIP_PATH = BUILD_DIR / "test-server-modpack.zip"
RELEASE_INFO_PATH = BUILD_DIR / "release-info.json"
USER_AGENT = "najaewon-modding/test-server-modpack"
CATEGORIES = ("required", "recommended")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
RELEASE_TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)(?:-build\.\d+)?$")


def request_json(url, github=False, allow_not_found=False):
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if github and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return None
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


def required(mapping, key):
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Missing or invalid {key!r} in manifest entry: {mapping}")
    return value


def parse_semver(version):
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise RuntimeError(f"Modpack version must use MAJOR.MINOR.PATCH format, got {version!r}")
    return tuple(int(part) for part in match.groups())


def bump_patch(version):
    major, minor, patch = parse_semver(version)
    return f"{major}.{minor}.{patch + 1}"


def mod_category(mod):
    category = mod.get("category", "required")
    if category not in CATEGORIES:
        raise RuntimeError(f"{mod.get('name', '<unnamed>')}: category must be one of {', '.join(CATEGORIES)}, got {category!r}")
    return category


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pack"), dict) or not isinstance(manifest.get("mods"), list):
        raise RuntimeError("manifest.json must contain a 'pack' object and a 'mods' array")
    for key in ("name", "version", "minecraft", "neoforge"):
        required(manifest["pack"], key)
    parse_semver(manifest["pack"]["version"])
    enabled = [mod for mod in manifest["mods"] if mod.get("enabled", True)]
    if not enabled:
        raise RuntimeError("At least one mod must be enabled")
    names = [required(mod, "name") for mod in enabled]
    if len(names) != len(set(names)):
        raise RuntimeError("Enabled mod names must be unique")
    for mod in enabled:
        mod_category(mod)
        source = required(mod, "source")
        required(mod, "version")
        if source == "github_release":
            required(mod, "repository")
            required(mod, "artifact")
        elif source == "modrinth":
            required(mod, "version_id")
            required(mod, "asset")
        else:
            raise RuntimeError(f"{mod['name']}: unsupported source {source!r}")


def mod_distribution_record(mod):
    source = required(mod, "source")
    record = {
        "name": required(mod, "name"),
        "category": mod_category(mod),
        "source": source,
        "version": required(mod, "version"),
    }
    if source == "github_release":
        record.update({
            "repository": required(mod, "repository"),
            "artifact": required(mod, "artifact"),
            "tag": mod.get("tag"),
            "asset": mod.get("asset"),
            "sha256": mod.get("sha256"),
        })
    elif source == "modrinth":
        record.update({
            "project_id": mod.get("project_id"),
            "version_id": required(mod, "version_id"),
            "asset": required(mod, "asset"),
            "sha256": mod.get("sha256"),
        })
    return record


def distribution_signature(manifest):
    return {
        "minecraft": manifest["pack"]["minecraft"],
        "neoforge": manifest["pack"]["neoforge"],
        "mods": sorted(
            (mod_distribution_record(mod) for mod in manifest["mods"] if mod.get("enabled", True)),
            key=lambda item: item["name"],
        ),
    }


def load_previous_release():
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        return None
    release = request_json(f"https://api.github.com/repos/{repository}/releases/latest", github=True, allow_not_found=True)
    if not release:
        return None
    tag = release.get("tag_name")
    match = RELEASE_TAG_RE.fullmatch(tag or "")
    if not match:
        raise RuntimeError(f"Latest release tag {tag!r} does not match vMAJOR.MINOR.PATCH[-build.N]")
    version = match.group(1)
    ref = urllib.parse.quote(tag, safe="")
    content = request_json(f"https://api.github.com/repos/{repository}/contents/manifest.json?ref={ref}", github=True, allow_not_found=True)
    if not content or content.get("encoding") != "base64" or not content.get("content"):
        raise RuntimeError(f"Latest release {tag} does not contain a readable manifest.json")
    raw = base64.b64decode(content["content"]).decode("utf-8")
    manifest = json.loads(raw)
    validate_manifest(manifest)
    return {"tag": tag, "version": version, "manifest": manifest}


def determine_release_version(manifest, previous):
    requested = manifest["pack"]["version"]
    if previous is None:
        return requested, True, "initial"
    changed = distribution_signature(manifest) != distribution_signature(previous["manifest"])
    previous_version = previous["version"]
    if not changed:
        if parse_semver(requested) > parse_semver(previous_version):
            raise RuntimeError(
                f"pack.version was changed to {requested}, but the distributed mod configuration is unchanged from {previous['tag']}. "
                "Change the modpack configuration in the same manifest update, or restore pack.version."
            )
        return previous_version, False, "unchanged"
    if parse_semver(requested) > parse_semver(previous_version):
        return requested, True, "manual"
    return bump_patch(previous_version), True, "automatic"


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


def enabled_mod_map(manifest):
    if not manifest:
        return {}
    return {mod["name"]: mod for mod in manifest.get("mods", []) if mod.get("enabled", True)}


def manifest_changes(previous_manifest, current_manifest, previous_version, effective_version):
    previous_mods = enabled_mod_map(previous_manifest)
    current_mods = enabled_mod_map(current_manifest)
    added, removed, updated, category_changed, source_changed = [], [], [], [], []

    for name in sorted(current_mods.keys() - previous_mods.keys()):
        mod = current_mods[name]
        added.append({"name": name, "version": mod["version"], "category": mod_category(mod)})

    for name in sorted(previous_mods.keys() - current_mods.keys()):
        mod = previous_mods[name]
        removed.append({"name": name, "version": mod["version"], "category": mod_category(mod)})

    for name in sorted(current_mods.keys() & previous_mods.keys()):
        old, new = previous_mods[name], current_mods[name]
        if old.get("version") != new.get("version"):
            updated.append({
                "name": name,
                "old_version": old.get("version", "?"),
                "new_version": new.get("version", "?"),
                "category": mod_category(new),
            })
        old_category, new_category = mod_category(old), mod_category(new)
        if old_category != new_category:
            category_changed.append({"name": name, "old_category": old_category, "new_category": new_category})
        old_record, new_record = mod_distribution_record(old), mod_distribution_record(new)
        for key in ("version", "category"):
            old_record.pop(key, None)
            new_record.pop(key, None)
        if old_record != new_record:
            source_changed.append({"name": name})

    platform_changes = []
    if previous_manifest:
        for key, label in (("minecraft", "Minecraft"), ("neoforge", "NeoForge")):
            old = previous_manifest.get("pack", {}).get(key)
            new = current_manifest.get("pack", {}).get(key)
            if old != new:
                platform_changes.append({"name": label, "old": old, "new": new})

    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "category_changed": category_changed,
        "source_changed": source_changed,
        "platform_changed": platform_changes,
        "pack_version_changed": previous_version is not None and previous_version != effective_version,
        "old_pack_version": previous_version,
        "new_pack_version": effective_version,
    }


def release_change_lines(changes, previous_tag):
    lines = ["", "## Changes"]
    if previous_tag:
        lines.extend(["", f"Compared with `{previous_tag}`."])
    if changes["pack_version_changed"]:
        lines.extend(["", f"- **Modpack version:** {changes['old_pack_version']} → {changes['new_pack_version']}"])
    if changes["platform_changed"]:
        lines.extend(["", "### Platform", ""])
        lines.extend(f"- **{item['name']}**: {item['old']} → {item['new']}" for item in changes["platform_changed"])
    sections = [
        ("Added Mods", changes["added"], lambda x: f"- **{x['name']}** {x['version']} (`{x['category']}`)"),
        ("Updated Mods", changes["updated"], lambda x: f"- **{x['name']}**: {x['old_version']} → {x['new_version']} (`{x['category']}`)"),
        ("Removed Mods", changes["removed"], lambda x: f"- **{x['name']}** {x['version']} (`{x['category']}`)"),
        ("Category Changes", changes["category_changed"], lambda x: f"- **{x['name']}**: `{x['old_category']}` → `{x['new_category']}`"),
        ("Distribution Target Changes", changes["source_changed"], lambda x: f"- **{x['name']}**"),
    ]
    any_changes = bool(changes["platform_changed"])
    for title, items, formatter in sections:
        if items:
            any_changes = True
            lines.extend(["", f"### {title}", ""])
            lines.extend(formatter(item) for item in items)
    if not any_changes and not changes["pack_version_changed"]:
        lines.extend(["", "No distributed modpack changes in this build."])
    return lines


def discord_change_text(changes):
    blocks = []
    if changes["pack_version_changed"]:
        blocks.append(f"**모드팩 버전**\n{changes['old_pack_version']} → {changes['new_pack_version']}")
    if changes["platform_changed"]:
        blocks.append("**플랫폼 변경**\n" + "\n".join(f"• {x['name']}: {x['old']} → {x['new']}" for x in changes["platform_changed"]))
    if changes["added"]:
        blocks.append("**추가된 모드**\n" + "\n".join(f"• {x['name']} {x['version']} ({x['category']})" for x in changes["added"]))
    if changes["updated"]:
        blocks.append("**업데이트된 모드**\n" + "\n".join(f"• {x['name']}: {x['old_version']} → {x['new_version']}" for x in changes["updated"]))
    if changes["removed"]:
        blocks.append("**제거된 모드**\n" + "\n".join(f"• {x['name']} {x['version']} ({x['category']})" for x in changes["removed"]))
    if changes["category_changed"]:
        blocks.append("**분류 변경**\n" + "\n".join(f"• {x['name']}: {x['old_category']} → {x['new_category']}" for x in changes["category_changed"]))
    if changes["source_changed"]:
        blocks.append("**배포 대상 변경**\n" + "\n".join(f"• {x['name']}" for x in changes["source_changed"]))
    return "\n\n".join(blocks) if blocks else "모드 구성 변경 없음"


def write_discord_payload(manifest, changes, effective_version):
    repository = os.environ.get("GITHUB_REPOSITORY", "najaewon-modding/test-server-modpack")
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "")
    tag = f"v{effective_version}-build.{run_number}" if run_number else ""
    release_url = f"https://github.com/{repository}/releases/tag/{tag}" if tag else f"https://github.com/{repository}/releases/latest"
    download_url = f"https://github.com/{repository}/releases/latest/download/test-server-modpack.zip"
    payload = {
        "username": "Test Server Modpack",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": f"테스트 서버 모드팩 {effective_version}",
            "url": release_url,
            "description": "새 모드팩이 배포되었습니다.",
            "fields": [
                {"name": "변경 사항", "value": discord_change_text(changes)[:1024], "inline": False},
                {"name": "다운로드", "value": f"[최신 모드팩 ZIP 다운로드]({download_url})", "inline": False},
                {"name": "설치", "value": "압축 파일에 있는 설치 가이드를 참고해주세요", "inline": False},
            ],
            "footer": {"text": f"Minecraft {manifest['pack']['minecraft']} · NeoForge {manifest['pack']['neoforge']}"},
        }],
    }
    (BUILD_DIR / "discord-payload.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_metadata(manifest, package_manifest, resolved, previous_tag, changes, effective_version):
    pack = package_manifest["pack"]
    mods_lines = [
        f"{pack['name']} {effective_version}",
        f"Minecraft {pack['minecraft']}",
        f"NeoForge {pack['neoforge']}",
    ]
    for category in CATEGORIES:
        title = "Required mods" if category == "required" else "Recommended mods"
        mods_lines.extend(["", f"{title}:"])
        items = [item for item in resolved if item["category"] == category]
        mods_lines.extend((f"- {item['name']} {item['version']} ({item['filename']})" for item in items) if items else ["- None"])
    (PACKAGE_DIR / "MODS.txt").write_text("\n".join(mods_lines) + "\n", encoding="utf-8")

    checksum_lines = [f"{item['sha256']}  {item['category']}/{item['filename']}" for item in resolved]
    (PACKAGE_DIR / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    enabled_mods = [mod for mod in manifest["mods"] if mod.get("enabled", True)]
    notices = []
    for mod, item in zip(enabled_mods, resolved):
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
    (PACKAGE_DIR / "manifest.json").write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not GUIDE_PATH.is_file():
        raise RuntimeError(f"Installation guide not found: {GUIDE_PATH.relative_to(ROOT)}")
    shutil.copy2(GUIDE_PATH, PACKAGE_DIR / "설치 가이드.html")

    notes = [
        f"# {pack['name']} {effective_version}",
        "",
        f"Automated test-server bundle for Minecraft **{pack['minecraft']}** and NeoForge **{pack['neoforge']}**.",
    ]
    notes.extend(release_change_lines(changes, previous_tag))
    for category in CATEGORIES:
        title = "Required Mods" if category == "required" else "Recommended Mods"
        notes.extend(["", f"## {title}", ""])
        notes.append("Install all of these mods before joining the test server." if category == "required" else "These mods are optional client-side additions recommended for the test server.")
        notes.append("")
        items = [item for item in resolved if item["category"] == category]
        notes.extend((f"- **{item['name']}** {item['version']}" for item in items) if items else ["- None"])
    notes.extend([
        "",
        "## Installation",
        "",
        "Please refer to `설치 가이드.html` included in `test-server-modpack.zip`.",
        "",
        "The ZIP includes the exact manifest and SHA-256 checksums used for this build.",
    ])
    third_party = [mod for mod in enabled_mods if mod.get("third_party")]
    if third_party:
        notes.extend(["", "## Third-party credits", ""])
        for mod in third_party:
            notes.append(f"- **{mod['name']}** by {mod.get('author', 'Unknown')} — {mod.get('homepage', '')}")
    (BUILD_DIR / "release-notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    write_discord_payload(package_manifest, changes, effective_version)


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
    previous = load_previous_release()
    effective_version, distribution_changed, version_mode = determine_release_version(manifest, previous)
    previous_version = previous["version"] if previous else None
    previous_manifest = previous["manifest"] if previous else None
    previous_tag = previous["tag"] if previous else None
    changes = manifest_changes(previous_manifest, manifest, previous_version, effective_version)

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    for category in CATEGORIES:
        (PACKAGE_DIR / category).mkdir(parents=True, exist_ok=True)

    resolved = []
    seen_files = set()
    for mod in manifest["mods"]:
        if not mod.get("enabled", True):
            continue
        category = mod_category(mod)
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
        destination = PACKAGE_DIR / category / filename
        print(f"Downloading {mod['name']} {mod['version']} -> {category}/{filename}")
        download(url, destination)
        actual_hash = sha256(destination)
        expected_hash = mod.get("sha256")
        if expected_hash and actual_hash.lower() != expected_hash.lower():
            raise RuntimeError(f"{mod['name']}: SHA-256 mismatch for {filename}: expected {expected_hash}, got {actual_hash}")
        resolved.append({"name": mod["name"], "category": category, "version": required(mod, "version"), "filename": filename, "sha256": actual_hash})

    package_manifest = copy.deepcopy(manifest)
    package_manifest["pack"]["version"] = effective_version
    write_metadata(manifest, package_manifest, resolved, previous_tag, changes, effective_version)
    create_zip()

    release_info = {
        "distribution_changed": distribution_changed,
        "previous_version": previous_version,
        "effective_version": effective_version,
        "version_mode": version_mode,
        "previous_tag": previous_tag,
    }
    RELEASE_INFO_PATH.write_text(json.dumps(release_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Built {ZIP_PATH.relative_to(ROOT)} with {len(resolved)} mods")
    print(f"Distribution changed: {distribution_changed}")
    print(f"Effective modpack version: {effective_version} ({version_mode})")
    if previous_tag:
        print(f"Compared with previous release {previous_tag}")
    else:
        print("No previous release found; treating this as the initial release")
    for item in resolved:
        print(f"  {item['sha256']}  {item['category']}/{item['filename']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
