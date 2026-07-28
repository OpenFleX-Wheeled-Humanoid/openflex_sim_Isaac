#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Open a generated OpenFlex Isaac scene.")
    parser.add_argument("--scene", default=str(repo_root / "artifacts" / "usd" / "scenes" / "openflex_empty_stage.usda"))
    parser.add_argument("--headless", default="false")
    parser.add_argument("--frames", type=int, default=0, help="When headless=true, step this many frames then exit.")
    return parser.parse_args()


ARGS = parse_args()

from isaacsim import SimulationApp


HEADLESS = ARGS.headless.lower() == "true"
SIMULATION_APP = SimulationApp(
    {
        "headless": HEADLESS,
        "hide_ui": HEADLESS,
        "renderer": "MinimalRendering" if HEADLESS else "RealTimePathTracing",
        "disable_viewport_updates": HEADLESS,
        "create_new_stage": False,
    }
)

import omni.timeline
import omni.kit.app
import omni.usd


def _enable_ui_tools() -> None:
    if HEADLESS:
        return
    extension_manager = omni.kit.app.get_app().get_extension_manager()
    extension_manager.set_extension_enabled_immediate("isaacsim.util.camera_inspector", True)


def main() -> None:
    scene_path = Path(ARGS.scene).resolve()
    if not scene_path.exists():
        raise FileNotFoundError(f"Scene not found: {scene_path}")

    if not omni.usd.get_context().open_stage(str(scene_path)):
        raise RuntimeError(f"Failed to open scene: {scene_path}")

    _enable_ui_tools()
    timeline = omni.timeline.get_timeline_interface()
    timeline.play()

    if HEADLESS and ARGS.frames > 0:
        for _ in range(ARGS.frames):
            SIMULATION_APP.update()
    else:
        while SIMULATION_APP.is_running():
            SIMULATION_APP.update()

    timeline.stop()
    SIMULATION_APP.close()


if __name__ == "__main__":
    main()
