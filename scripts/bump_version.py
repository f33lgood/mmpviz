#!/usr/bin/env python3
"""
bump_version.py — Prepare a version release for mmpviz.

Usage:
    python scripts/bump_version.py 1.0.0
    python scripts/bump_version.py 1.0.0 --dry-run  # preview without writing
    python scripts/bump_version.py --check           # show current version only

Updates scripts/version.py (the single source of truth).
pyproject.toml reads version dynamically from there — no edit needed.

Checklist printed after a successful bump:
  1. Review + commit the version bump.
  2. Add a dated release entry to CHANGELOG.md.
  3. git tag v<version> && git push origin v<version>
  4. Build and publish: python -m build && twine upload dist/*
     (or: uv build && uv publish)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

_REPO   = Path(__file__).resolve().parent.parent
_VER_PY = _REPO / "scripts" / "version.py"
_SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')


def current_version() -> str:
    text = _VER_PY.read_text()
    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text)
    if not m:
        sys.exit(f"error: cannot parse __version__ in {_VER_PY}")
    return m.group(1)


def check_changelog(version: str) -> bool:
    cl = _REPO / "CHANGELOG.md"
    if not cl.exists():
        return False
    return f"({version})" in cl.read_text()


def git_tag_exists(tag: str) -> bool:
    result = subprocess.run(
        ["git", "tag", "--list", tag],
        capture_output=True, text=True, cwd=_REPO
    )
    return bool(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", nargs="?", help="New version (e.g. 1.0.0)")
    parser.add_argument("--check", action="store_true", help="Print current version and exit")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing any files")
    args = parser.parse_args()

    if args.check or args.version is None:
        print(f"current version: {current_version()}")
        return

    new_ver = args.version.lstrip("v")
    if not _SEMVER.match(new_ver):
        sys.exit(f"error: '{new_ver}' is not valid semver (expected x.y.z)")

    old_ver = current_version()
    if new_ver == old_ver:
        sys.exit(f"error: version is already {old_ver}")

    # Update version.py
    old_text = _VER_PY.read_text()
    new_text = re.sub(
        r"(__version__\s*=\s*)['\"][^'\"]+['\"]",
        rf"\g<1>'{new_ver}'",
        old_text,
    )
    if new_text == old_text:
        sys.exit(f"error: could not replace version in {_VER_PY}")
    if args.dry_run:
        print(f"[dry-run] scripts/version.py  {old_ver} → {new_ver}")
    else:
        _VER_PY.write_text(new_text)
        print(f"✓ scripts/version.py  {old_ver} → {new_ver}")

    # Warnings
    if git_tag_exists(f"v{new_ver}"):
        print(f"⚠  git tag v{new_ver} already exists")

    if not check_changelog(new_ver):
        print(f"⚠  CHANGELOG.md has no entry for ({new_ver}) — add one before tagging")

    print()
    print("Next steps:")
    print(f"  1. git add scripts/version.py && git commit -m 'chore: bump version to {new_ver}'")
    print(f"  2. Update CHANGELOG.md: change the draft [YYYY-MM-DD] heading to [YYYY-MM-DD] ({new_ver})")
    print(f"  3. git tag v{new_ver} && git push origin main v{new_ver}")
    print(f"  4. python -m build && twine upload dist/*")
    print(f"     (or: uv build && uv publish)")


if __name__ == "__main__":
    main()
