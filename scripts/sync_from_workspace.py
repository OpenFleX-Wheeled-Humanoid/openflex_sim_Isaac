#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sources.json"
PACKAGES_ROOT = REPO_ROOT / "packages"
MANIFEST_PATH = REPO_ROOT / "docs" / "source_manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync source packages from the local ROS workspace snapshot.")
    parser.add_argument("--workspace-root", default=None)
    parser.add_argument("--clean", action="store_true", help="Delete destination package directories before copying.")
    return parser.parse_args()


def _ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {".git", "__pycache__"}
    return {name for name in names if name in ignored}


def _copy_tree(src: Path, dst: Path, clean: bool) -> None:
    if clean and dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore)


def main() -> int:
    args = parse_args()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    workspace_root = Path(args.workspace_root or config["workspace_root"]).resolve()

    manifest: dict[str, object] = {
        "source": "workspace",
        "workspace_root": str(workspace_root),
        "packages": {},
    }

    for package_name, package_config in config["packages"].items():
        src = workspace_root / package_config["workspace_path"]
        dst = PACKAGES_ROOT / package_name
        if not src.exists():
            raise FileNotFoundError(f"Workspace source does not exist: {src}")
        _copy_tree(src, dst, clean=args.clean)
        manifest["packages"][package_name] = {"source_path": str(src), "destination_path": str(dst)}
        print(f"Synced {package_name}: {src} -> {dst}")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote manifest to {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
