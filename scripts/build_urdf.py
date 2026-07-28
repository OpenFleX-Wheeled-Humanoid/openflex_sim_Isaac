#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONFIG_PATH = REPO_ROOT / "configs" / "sources.json"
DEFAULT_XACRO = PACKAGES_ROOT / "openarmx_integrated_description" / "urdf" / "openarmx_integrated_robot.urdf.xacro"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "urdf" / "openflex_integrated_robot.urdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile the OpenFlex integrated xacro into a plain URDF.")
    parser.add_argument("--xacro", default=str(DEFAULT_XACRO))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--packages-root", default=str(PACKAGES_ROOT))
    return parser.parse_args()


def _load_package_map(packages_root: Path) -> dict[str, Path]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    package_names = list(config["packages"].keys())
    package_map: dict[str, Path] = {}
    for name in package_names:
        if name == "openflex_chassis":
            package_map["swerve_description"] = packages_root / "openflex_chassis" / "swerve_description"
        package_map[name] = packages_root / name
    return package_map


def _inject_fake_ament(package_map: dict[str, Path]) -> None:
    if "ament_index_python" in sys.modules:
        return

    resolved = {name: str(path.resolve()) for name, path in package_map.items() if path.exists()}
    ament_index = types.ModuleType("ament_index_python")
    ament_index.__path__ = []
    ament_packages = types.ModuleType("ament_index_python.packages")
    ament_packages.__package__ = "ament_index_python"

    def get_package_share_directory(package_name: str) -> str:
        if package_name in resolved:
            return resolved[package_name]
        raise FileNotFoundError(
            f"package '{package_name}' not found under {PACKAGES_ROOT}. "
            "Run scripts/sync_from_workspace.py or scripts/update_from_upstream.py first."
        )

    ament_packages.get_package_share_directory = get_package_share_directory
    sys.modules["ament_index_python"] = ament_index
    sys.modules["ament_index_python.packages"] = ament_packages


def main() -> int:
    args = parse_args()
    xacro_path = Path(args.xacro).resolve()
    output_path = Path(args.output).resolve()
    packages_root = Path(args.packages_root).resolve()

    if not xacro_path.exists():
        print(f"xacro source not found: {xacro_path}", file=sys.stderr)
        return 1

    try:
        import xacro
    except ImportError:
        print("xacro is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    package_map = _load_package_map(packages_root)
    _inject_fake_ament(package_map)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        doc = xacro.process_file(str(xacro_path))
    except Exception as exc:
        print(f"xacro compilation failed: {exc}", file=sys.stderr)
        return 1

    output_path.write_text(doc.toprettyxml(indent="  "), encoding="utf-8")
    print(f"Wrote URDF to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
