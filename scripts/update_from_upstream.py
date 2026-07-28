#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sources.json"
PACKAGES_ROOT = REPO_ROOT / "packages"
CACHE_ROOT = REPO_ROOT / ".cache" / "upstream"
MANIFEST_PATH = REPO_ROOT / "docs" / "source_manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch the latest upstream OpenFlex description repos and sync them locally.")
    parser.add_argument("--clean", action="store_true", help="Delete destination package directories before copying.")
    return parser.parse_args()


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in {".git", "__pycache__"}}


def _copy_tree(src: Path, dst: Path, clean: bool) -> None:
    if clean and dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore)


def _sync_repo(name: str, url: str, branch: str) -> Path:
    checkout_dir = CACHE_ROOT / name
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    if not checkout_dir.exists():
        _run(["git", "clone", "--branch", branch, "--single-branch", url, str(checkout_dir)])
    else:
        _run(["git", "fetch", "origin", branch], cwd=checkout_dir)
        _run(["git", "checkout", branch], cwd=checkout_dir)
        _run(["git", "pull", "--ff-only", "origin", branch], cwd=checkout_dir)
    return checkout_dir


def main() -> int:
    args = parse_args()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    manifest: dict[str, object] = {
        "source": "upstream",
        "packages": {},
    }

    for package_name, package_config in config["packages"].items():
        checkout_dir = _sync_repo(package_name, package_config["upstream_url"], package_config["branch"])
        dst = PACKAGES_ROOT / package_name
        _copy_tree(checkout_dir, dst, clean=args.clean)
        manifest["packages"][package_name] = {
            "upstream_url": package_config["upstream_url"],
            "branch": package_config["branch"],
            "cache_path": str(checkout_dir),
            "destination_path": str(dst),
        }
        print(f"Updated {package_name} from {package_config['upstream_url']}")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote manifest to {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
