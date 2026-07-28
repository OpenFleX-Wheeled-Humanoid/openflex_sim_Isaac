#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Import the OpenFlex URDF into USD and build a ready-to-open Isaac scene.")
    parser.add_argument("--urdf", default=str(repo_root / "artifacts" / "urdf" / "openflex_integrated_robot.urdf"))
    parser.add_argument("--robot-output-dir", default=str(repo_root / "artifacts" / "usd" / "robots"))
    parser.add_argument("--scene-output", default=str(repo_root / "artifacts" / "usd" / "scenes" / "openflex_empty_stage.usda"))
    parser.add_argument("--headless", default="true")
    parser.add_argument("--fix-base", default="false")
    return parser.parse_args()


ARGS = parse_args()

from isaacsim import SimulationApp


HEADLESS = ARGS.headless.lower() == "true"
FIX_BASE = ARGS.fix_base.lower() == "true"
REPO_ROOT = Path(__file__).resolve().parents[1]

# Conservative initial tuning for the 8.47 kg lift carriage and its mounted upper body.
# Keep these values in SI units because the URDF importer can convert a prismatic
# joint velocity as though it were angular.
LIFT_DRIVE_STIFFNESS = 2500.0  # N / m
LIFT_DRIVE_DAMPING = 300.0  # N * s / m
LIFT_DRIVE_MAX_FORCE = 500.0  # N
LIFT_MAX_VELOCITY = 0.10  # m / s

SIMULATION_APP = SimulationApp(
    {
        "headless": HEADLESS,
        "hide_ui": HEADLESS,
        "renderer": "MinimalRendering" if HEADLESS else "RealTimePathTracing",
        "disable_viewport_updates": HEADLESS,
        "create_new_stage": False,
        "active_gpu": 0,
        "physics_gpu": 0,
        "multi_gpu": False,
        "max_gpu_count": 1,
    }
)

import carb
import omni.kit.app
import omni.usd
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics


def _flush_updates(frames: int = 30) -> None:
    for _ in range(frames):
        SIMULATION_APP.update()


def _enable_extensions() -> None:
    ext_manager = omni.kit.app.get_app().get_extension_manager()
    for name in ("isaacsim.asset.importer.urdf", "isaacsim.sensors.experimental.rtx"):
        ext_manager.set_extension_enabled_immediate(name, True)


def _set_xform(prim, translation: Gf.Vec3d | None = None) -> None:
    xformable = UsdGeom.Xformable(prim)
    ops = {op.GetOpName(): op for op in xformable.GetOrderedXformOps()}
    if translation is not None:
        translate_op = ops.get("xformOp:translate") or xformable.AddTranslateOp()
        translate_op.Set(translation)


def _set_pose(prim, translation: Gf.Vec3d, orientation: Gf.Quatf | None = None) -> None:
    _set_xform(prim, translation)
    if orientation is None:
        return
    xformable = UsdGeom.Xformable(prim)
    ops = {op.GetOpName(): op for op in xformable.GetOrderedXformOps()}
    orient_op = ops.get("xformOp:orient") or xformable.AddOrientOp(UsdGeom.XformOp.PrecisionFloat)
    orient_op.Set(orientation)


def _get_translation(prim) -> Gf.Vec3d:
    xformable = UsdGeom.Xformable(prim)
    for op in xformable.GetOrderedXformOps():
        if op.GetOpName() == "xformOp:translate":
            value = op.Get()
            coords = [float(value[0]), float(value[1]), float(value[2])]
            if any((not abs(coord) < 1.0e6) for coord in coords):
                return Gf.Vec3d(0.0, 0.0, 0.0)
            return Gf.Vec3d(coords[0], coords[1], coords[2])
    return Gf.Vec3d(0.0, 0.0, 0.0)


def _ensure_physics_scene(stage) -> None:
    scene = stage.GetPrimAtPath("/World/physicsScene")
    if scene.IsValid():
        return
    scene_api = UsdPhysics.Scene.Define(stage, Sdf.Path("/World/physicsScene"))
    scene_api.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
    scene_api.CreateGravityMagnitudeAttr().Set(9.81)


def _ensure_environment(stage) -> None:
    from isaacsim.core.experimental.materials import RigidBodyMaterial
    from isaacsim.core.experimental.objects import GroundPlane

    UsdGeom.Xform.Define(stage, Sdf.Path("/World/Environment"))

    if not stage.GetPrimAtPath("/World/Environment/DomeLight").IsValid():
        dome_light = UsdLux.DomeLight.Define(stage, Sdf.Path("/World/Environment/DomeLight"))
        dome_light.CreateIntensityAttr(1800.0)
        dome_light.CreateColorAttr(Gf.Vec3f(1.0, 0.98, 0.95))

    if not stage.GetPrimAtPath("/World/Environment/KeyLight").IsValid():
        key_light = UsdLux.DistantLight.Define(stage, Sdf.Path("/World/Environment/KeyLight"))
        key_light.CreateIntensityAttr(3500.0)
        key_light.CreateAngleAttr(0.7)
        key_light.CreateColorAttr(Gf.Vec3f(1.0, 0.97, 0.92))

    if not stage.GetPrimAtPath("/World/Environment/GroundPlane").IsValid():
        ground_plane = GroundPlane("/World/Environment/GroundPlane", sizes=80.0, templates="wireframe-blue")
        ground_plane.set_offsets(contact_offsets=[0.02], rest_offsets=[0.0])
        ground_material = RigidBodyMaterial(
            "/World/Environment/PhysicsMaterials/ground",
            static_frictions=[1.0],
            dynamic_frictions=[0.85],
            restitutions=[0.0],
        )
        ground_plane.apply_physics_materials(ground_material)


def _position_prim_on_ground(stage, prim_path: str) -> None:
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return
    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    aligned_box = bbox_cache.ComputeWorldBound(prim).ComputeAlignedBox()
    min_z = float(aligned_box.GetMin()[2])
    clearance = 0.005
    offset_z = clearance - min_z
    if abs(offset_z) < 1e-4:
        return
    current_translation = _get_translation(prim)
    _set_xform(
        prim,
        translation=Gf.Vec3d(
            current_translation[0],
            current_translation[1],
            current_translation[2] + offset_z,
        ),
    )


def _find_articulation_root(stage, root_prim=None) -> str | None:
    iterator = Usd.PrimRange(root_prim) if root_prim is not None else stage.Traverse()
    for prim in iterator:
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            return str(prim.GetPath())
    return None


def _configure_articulation_stability(stage, articulation_path: str) -> None:
    articulation_prim = stage.GetPrimAtPath(articulation_path)
    if not articulation_prim or not articulation_prim.IsValid():
        return
    api = PhysxSchema.PhysxArticulationAPI.Apply(articulation_prim)
    api.CreateSolverPositionIterationCountAttr().Set(32)
    api.CreateSolverVelocityIterationCountAttr().Set(4)
    api.CreateSleepThresholdAttr().Set(0.0)
    api.CreateStabilizationThresholdAttr().Set(0.0)


def _configure_lift_drive(stage, root_prim) -> None:
    """Apply the lift's final USD settings after URDF import.

    The importer currently leaves the URDF damping on this joint and converts its
    0.10 m/s velocity limit to 5.729578, as though the prismatic joint were angular.
    Writing the USD APIs directly keeps the saved asset in SI units.
    """
    for prim in Usd.PrimRange(root_prim):
        if prim.GetName() != "lift_joint" or not prim.IsA(UsdPhysics.PrismaticJoint):
            continue

        drive = UsdPhysics.DriveAPI.Get(prim, "linear")
        if not drive:
            drive = UsdPhysics.DriveAPI.Apply(prim, "linear")
        drive.CreateTypeAttr().Set("force")
        drive.CreateStiffnessAttr().Set(LIFT_DRIVE_STIFFNESS)
        drive.CreateDampingAttr().Set(LIFT_DRIVE_DAMPING)
        drive.CreateMaxForceAttr().Set(LIFT_DRIVE_MAX_FORCE)

        joint_api = PhysxSchema.PhysxJointAPI.Apply(prim)
        joint_api.CreateMaxJointVelocityAttr().Set(LIFT_MAX_VELOCITY)
        return

    raise RuntimeError(f"Could not find prismatic lift_joint below {root_prim.GetPath()}")


def _find_link(stage, root_prim, link_name: str):
    for prim in Usd.PrimRange(root_prim):
        if prim.GetName() == link_name and prim.HasAPI(UsdPhysics.RigidBodyAPI):
            return prim
    raise RuntimeError(f"Could not find rigid link '{link_name}' below {root_prim.GetPath()}")


def _create_sensor_mount(stage, link_prim, name: str, translation: Gf.Vec3d, orientation: Gf.Quatf | None = None):
    sensors_path = link_prim.GetPath().AppendChild("Sensors")
    UsdGeom.Xform.Define(stage, sensors_path)
    mount = UsdGeom.Xform.Define(stage, sensors_path.AppendChild(name)).GetPrim()
    _set_pose(mount, translation, orientation)
    return mount


def _mark_camera_outputs(camera_prim, outputs: list[str]) -> None:
    camera_prim.CreateAttribute("openflex:sensor:outputs", Sdf.ValueTypeNames.StringArray, custom=True).Set(outputs)


def _add_sensors(stage, robot_root) -> None:
    """Author reusable RTX sensor prims at the physical sensor mounting frames."""
    from isaacsim.sensors.experimental.rtx import Lidar, RtxCamera

    base_link = _find_link(stage, robot_root, "base_link")
    head_yaw_link = _find_link(stage, robot_root, "head_yaw_link")

    # D435: the URDF mount is at the base-link origin plus (0.36, 0, 0.055).
    # USD cameras look along local -Z, so rotate that axis toward the robot +X direction.
    d435_mount = _create_sensor_mount(
        stage,
        base_link,
        "ChassisD435",
        Gf.Vec3d(0.36, 0.0, 0.055),
        Gf.Quatf(0.70710677, Gf.Vec3f(0.0, -0.70710677, 0.0)),
    )
    rgb_camera = RtxCamera(str(d435_mount.GetPath().AppendChild("RgbCamera")), tick_rate=30.0)
    depth_camera = RtxCamera(str(d435_mount.GetPath().AppendChild("DepthCamera")), tick_rate=30.0)
    _mark_camera_outputs(rgb_camera.prims[0], ["rgb"])
    _mark_camera_outputs(depth_camera.prims[0], ["distance_to_image_plane"])

    # The head CAD contains a Femto Bolt camera mesh. Its visual origin supplies the
    # mount translation; the optical model can be refined once hardware calibration is available.
    head_mount = _create_sensor_mount(
        stage,
        head_yaw_link,
        "HeadCamera",
        Gf.Vec3d(-0.5631, 0.0824, -0.1072),
    )
    head_camera = RtxCamera(str(head_mount.GetPath().AppendChild("RgbCamera")), tick_rate=30.0)
    _mark_camera_outputs(head_camera.prims[0], ["rgb"])

    # Livox Mid-360 is not present in Isaac Sim's official sensor registry. Use the
    # official solid-state RTX lidar as an operational baseline at the URDF Livox frame.
    lidar_mount = _create_sensor_mount(
        stage,
        base_link,
        "Mid360Lidar",
        Gf.Vec3d(0.3, 0.0, 0.12),
        Gf.Quatf(0.6830127, Gf.Vec3f(-0.1830127, 0.1830127, -0.6830127)),
    )
    lidar = Lidar.create(
        path=str(lidar_mount.GetPath().AppendChild("PointCloud")),
        config="Example_Solid_State",
        tick_rate=10.0,
        aux_output_level="BASIC",
    )
    lidar.prims[0].CreateAttribute(
        "openflex:sensor:outputs", Sdf.ValueTypeNames.StringArray, custom=True
    ).Set(["generic-model-output"])


def _ros_package_paths() -> list[dict[str, str]]:
    config = json.loads((REPO_ROOT / "configs" / "sources.json").read_text(encoding="utf-8"))
    result: list[dict[str, str]] = []
    for package_name in config["packages"].keys():
        package_root = REPO_ROOT / "packages" / package_name
        if package_root.exists():
            result.append({"name": package_name, "path": str(package_root.resolve())})
    swerve_description = REPO_ROOT / "packages" / "openflex_chassis" / "swerve_description"
    if swerve_description.exists():
        result.append({"name": "swerve_description", "path": str(swerve_description.resolve())})
    return result


def _import_urdf(urdf_path: str, output_dir: str) -> str:
    from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig

    config = URDFImporterConfig()
    config.urdf_path = urdf_path
    config.usd_path = output_dir
    config.ros_package_paths = _ros_package_paths()
    config.fix_base = FIX_BASE
    config.merge_fixed_joints = True
    config.merge_mesh = False
    config.collision_from_visuals = False
    config.allow_self_collision = False
    config.joint_drive_type = {
        r".*": "force",
    }
    config.joint_target_type = "position"
    config.override_joint_stiffness = {
        r"^lift_joint$": LIFT_DRIVE_STIFFNESS,
        r"^openarmx_head_(yaw|pitch)_joint$": 400.0,
        r"^openarmx_(left|right)_joint[1-7]$": 800.0,
        r"^openarmx_(left|right)_finger_joint[12]$": 200.0,
        r"^(fl|fr|bl|br)_steering_joint$": 1200.0,
        r"^(fl|fr|bl|br)_wheel_joint$": 0.0,
    }
    config.override_joint_damping = {
        r"^lift_joint$": LIFT_DRIVE_DAMPING,
        r"^openarmx_head_(yaw|pitch)_joint$": 40.0,
        r"^openarmx_(left|right)_joint[1-7]$": 80.0,
        r"^openarmx_(left|right)_finger_joint[12]$": 20.0,
        r"^(fl|fr|bl|br)_steering_joint$": 120.0,
        r"^(fl|fr|bl|br)_wheel_joint$": 80.0,
    }
    config.run_asset_transformer = False
    importer = URDFImporter(config)
    return os.path.normpath(importer.import_urdf())


def _wait_for_stage() -> Usd.Stage:
    for _ in range(240):
        SIMULATION_APP.update()
        if omni.usd.get_context().get_stage_loading_status()[2] == 0:
            break
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("Stage is unavailable")
    return stage


def _create_scene(robot_usd_path: str, scene_output: str) -> None:
    omni.usd.get_context().new_stage()
    _flush_updates(30)
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("Failed to create a new stage")

    world = UsdGeom.Xform.Define(stage, Sdf.Path("/World"))
    stage.SetDefaultPrim(world.GetPrim())

    robot = UsdGeom.Xform.Define(stage, Sdf.Path("/World/OpenFlex"))
    robot.GetPrim().GetReferences().AddReference(os.path.abspath(robot_usd_path))
    _flush_updates(120)

    _ensure_physics_scene(stage)
    _ensure_environment(stage)

    articulation_path = _find_articulation_root(stage, stage.GetPrimAtPath("/World/OpenFlex"))
    if articulation_path is not None:
        _configure_articulation_stability(stage, articulation_path)

    scene_output_path = Path(scene_output)
    scene_output_path.parent.mkdir(parents=True, exist_ok=True)
    if not omni.usd.get_context().save_as_stage(str(scene_output_path)):
        raise RuntimeError(f"Failed to save stage to {scene_output_path}")


def _normalize_robot_asset(robot_usd_path: str) -> None:
    if not omni.usd.get_context().open_stage(robot_usd_path):
        raise RuntimeError(f"Failed to open robot USD stage: {robot_usd_path}")

    _flush_updates(120)
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("Robot USD stage is unavailable")

    default_prim = stage.GetDefaultPrim()
    if default_prim and default_prim.IsValid():
        _position_prim_on_ground(stage, str(default_prim.GetPath()))
        _configure_lift_drive(stage, default_prim)
        articulation_path = _find_articulation_root(stage, default_prim)
        if articulation_path is not None:
            _configure_articulation_stability(stage, articulation_path)
        _add_sensors(stage, default_prim)

    if not omni.usd.get_context().save_as_stage(str(Path(robot_usd_path).resolve())):
        raise RuntimeError(f"Failed to save normalized robot USD stage: {robot_usd_path}")


def main() -> None:
    urdf_path = Path(ARGS.urdf).resolve()
    robot_output_dir = Path(ARGS.robot_output_dir).resolve()
    if robot_output_dir.exists():
        shutil.rmtree(robot_output_dir)
    robot_output_dir.mkdir(parents=True, exist_ok=True)

    if not urdf_path.exists():
        raise FileNotFoundError(f"URDF does not exist: {urdf_path}")

    carb.log_info("Enabling Isaac Sim URDF importer extension")
    _enable_extensions()
    _flush_updates(60)

    carb.log_info(f"Importing URDF {urdf_path}")
    robot_usd_path = _import_urdf(str(urdf_path), str(robot_output_dir))
    _normalize_robot_asset(robot_usd_path)
    carb.log_info(f"Robot USD written to {robot_usd_path}")

    carb.log_info("Building a ready-to-open Isaac scene around the imported robot")
    _create_scene(robot_usd_path, ARGS.scene_output)
    carb.log_info(f"Scene USD written to {Path(ARGS.scene_output).resolve()}")

    SIMULATION_APP.close()


if __name__ == "__main__":
    main()
