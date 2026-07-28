[📗 English](README.md)

# openflex_sim_Isaac

![OpenFlex Isaac Sim](assets/主页动画.gif)

OpenFlex 轮式人形机器人的 Isaac Sim 资产仓库。仓库已包含可直接运行的机器人 USD 和场景 USD。

## Quick Start

前提：已安装 Isaac Sim，且 NVIDIA 驱动可正常工作。无需 ROS 2，也无需构建 URDF 或 USD。

```bash
git clone <repo-url> openflex_sim_Isaac
cd openflex_sim_Isaac

export ISAAC_SIM_PYTHON=/path/to/isaacsim/python.sh
"$ISAAC_SIM_PYTHON" scripts/open_scene.py
```

例如，Isaac Sim 安装在 `/home/openflex/isaacsim`：

```bash
export ISAAC_SIM_PYTHON=/home/openflex/isaacsim/python.sh
"$ISAAC_SIM_PYTHON" scripts/open_scene.py
```

`open_scene.py` 默认启动带界面的 Isaac Sim，并打开：

```text
artifacts/usd/scenes/openflex_empty_stage.usda
```

该场景已包含 OpenFlex 机器人、物理场景、网格地板和基础灯光。

可选的无界面验证：

```bash
"$ISAAC_SIM_PYTHON" scripts/open_scene.py --headless true --frames 300
```

## 在 Isaac Sim 中使用

### 调节关节

打开 `Tools > Robotics > Joint Inspector`，在机器人下拉框中选择 `/World/OpenFlex`。

- 双臂、头部、转向关节和升降柱：修改 `Target Position`
- 四个轮子：修改 `Target Velocity`
- 需要调节控制效果时：修改 `Stiffness`、`Damping` 和 `Max Force`

修改目标值后点击播放。转动关节使用角度目标，升降柱和夹爪使用线性位置目标。

### 相机与 LiDAR

生成的 USD 包含以下 RTX 传感器：

- 底盘 D435：`ChassisD435/RgbCamera`，输出 RGB
- 底盘 D435：`ChassisD435/DepthCamera`，输出 `distance_to_image_plane` 深度
- 头部 Femto Bolt：`HeadCamera/RgbCamera`，输出 RGB
- `mid360_link`：`Mid360Lidar/PointCloud`，输出点云基础数据

打开 `Tools > Sensors > Camera Inspector`，选择任一 RGB 相机并点击 `Create Viewport`，即可查看相机画面。

深度图和 LiDAR 点云由 Isaac Sim 的运行时传感器管线读取：深度使用 `CameraSensor` 的 `distance_to_image_plane` annotator，LiDAR 使用 `LidarSensor` 的 `generic-model-output`。后续 ROS 2 集成可将这些数据发布为图像、`CameraInfo` 和 `PointCloud2` 话题。

`mid360_link` 是 LiDAR，不是毫米波雷达。当前使用 Isaac Sim 官方 `Example_Solid_State` LiDAR 作为运行基线；其官方 USD 通过网络引用，首次加载需要能访问 Isaac Sim 资产源。

## Assets

```text
artifacts/usd/robots/openflex_integrated_robot/openflex_integrated_robot.usda
artifacts/usd/scenes/openflex_empty_stage.usda
```

机器人资产和场景资产均可直接从 Isaac Sim 的 Stage 中打开或引用。场景通过相对路径引用机器人 USD，因此请保留 `artifacts/usd/` 内的目录结构。

## Rebuild Assets

仅在需要更新机器人描述文件或重新导入 USD 时执行本节。日常使用已提供的 USD 不需要此流程。

本仓库用 `uv` 管理 `xacro` 和同步工具的 Python 环境；Isaac Sim API 仍由 Isaac Sim 自带的 `python.sh` 运行。

```bash
uv sync
uv run scripts/sync_from_workspace.py --clean
uv run scripts/build_urdf.py
"$ISAAC_SIM_PYTHON" scripts/build_usd.py
```

如需从配置的上游仓库获取描述包，而非从本机 ROS 工作区同步：

```bash
uv run scripts/update_from_upstream.py --clean
uv run scripts/build_urdf.py
"$ISAAC_SIM_PYTHON" scripts/build_usd.py
```

使用 `--headless false` 可以在 USD 导入期间显示 Isaac Sim 窗口。

## Layout

```text
artifacts/        Generated URDF and ready-to-use USD assets
packages/         Snapshot of robot description packages
scripts/          Scene launcher and asset build tools
configs/          Source repository configuration
```

## Scripts

- `scripts/open_scene.py`: 打开已提供的 Isaac 场景
- `scripts/sync_from_workspace.py`: 从本地 ROS 工作区同步描述包
- `scripts/update_from_upstream.py`: 拉取并同步上游描述包
- `scripts/build_urdf.py`: 生成中间 URDF
- `scripts/build_usd.py`: 使用 Isaac Sim URDF Importer 重新生成 USD

## References

- [Isaac Sim URDF Importer](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/importer_exporter/ext_isaacsim_asset_importer_urdf.html)
- [Isaac Sim Standalone Python](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/python_scripting/manual_standalone_python.html)
- [Isaac Sim Joint Inspector](https://docs.isaacsim.omniverse.nvidia.com/latest/robot_setup/joint_inspector.html)
- [Isaac Sim Camera Sensors](https://docs.isaacsim.omniverse.nvidia.com/latest/sensors/isaacsim_sensors_camera.html)

## 当前状态

当前版本为初版。许多物理参数仍为预估值，需要结合实机数据和仿真测试继续标定；当前尚未集成底盘与上身的 IK 逆运动学解算。

## 许可证

本作品采用知识共享 署名-非商业性使用-相同方式共享 4.0 国际许可协议 (CC BY-NC-SA 4.0) 进行许可。

版权所有 (c) 2026 成都长数机器人有限公司 (Chengdu Changshu Robot Co., Ltd.)

详情请参阅 [LICENSE_CN.md](LICENSE) 文件或访问：http://creativecommons.org/licenses/by-nc-sa/4.0/

## 致谢

本包是 OpenArmX 机器人平台生态系统的一部分，专为协作机器人领域的研究和工业应用而开发。

---

## 📞 联系我们

### 成都长数机器人有限公司
**Chengdu Changshu Robotics Co., Ltd.**

| 联系方式 | 信息 |
|---------|------|
| 📧 邮箱 | openarmrobot@gmail.com |
| 📱 电话/微信 | +86-17746530375 |
| 🌐 官网 | <https://openarmx.com/> |
| 🌐 文档 | <http://docs.openarmx.com/> |
| 📍 地址 | 天津经济技术开发区西区新业八街11号华诚机械厂 |
| 👤 联系人 | 王先生 |
