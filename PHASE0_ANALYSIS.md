# Phase 0 源码分析 + fork/重写决策

> 分析对象: `EpicGamesExt/BlenderTools`(Send to Unreal),MIT 协议,可自由参考/复用(保留版权声明)。
> 本地副本: `reference/BlenderTools/`。分析日期 2026-09-26。

---

## 零、版本兼容性核实(UE 5.8 + Blender 5.1,已在本机实测)

> 目标环境: **Blender 5.1.0**(build 2026-03-17)+ **UE 5.8**(`D:\ue\UE_5.8`)。
> Send2UE 克隆到的实际版本 = **2.4.3**,`bl_info` 声明最低 `blender: (3,3,0)`,无上限、无 UE 版本 pin。
> (注: 网上流传的"2.6.5 支持 Blender 5.1+UE5.6"与源码对不上,以本地克隆为准。)

### Blender 5.1 端 —— 结构上兼容,需运行时验证
| 检查项 | 结果 |
|--------|------|
| 猴补丁目标模块 `io_scene_fbx/export_fbx_bin.py` 是否存在 | ✅ 存在,但**路径从 `scripts/addons/` 移到 `scripts/addons_core/`** |
| 4 个被猴补丁的函数(`fbx_animations_do`/`fbx_data_armature_elements`/`fbx_data_object_elements`/`fbx_data_bindpose_element`) | ✅ **全部还在** |
| `fbx_utils` 关键名(含 4.0 新增 `elem_data_single_char`) | ✅ 全部存在 |
| Send2UE 是否在 Blender 5.1 上测试过 | ❌ 未声明,`bl_info` 只到 3.3 最低版 |

**风险**: 函数"存在"是必要非充分条件——内部签名/行为可能在 4.x→5.x 间漂移。且 `fbx.py` 用 `addon_utils.modules()` 定位 `io_scene_fbx`,需确认 5.1 的 `addon_utils.modules()` 仍返回 `addons_core` 下的模块。**Phase 2 采纳猴补丁前必须在 5.1 上实跑验证。**

### UE 5.8 端 —— 控制通道协议完全一致
| 检查项 | UE 5.8 自带 | Send2UE vendored | 结论 |
|--------|------------|------------------|------|
| `_PROTOCOL_VERSION` | 1 | 1 | ✅ 一致 |
| `_PROTOCOL_MAGIC` | `'ue_py'` | `'ue_py'` | ✅ 一致 |
| 多播端点 | `239.0.0.1:6766` | `239.0.0.1:6766` | ✅ 一致 |
| 命令端点 | `127.0.0.1:6776` | `127.0.0.1:6776` | ✅ 一致 |
| 行数 | 649 | 640 | 仅 9 行注释级差异 |

**结论**: Remote Execution 协议兼容。**精简版可直接用 UE 5.8 自带的 `remote_execution.py`**(`D:\ue\UE_5.8\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python\remote_execution.py`),无需依赖 vendored 副本。

### 待 Phase 0(b) 运行时验证的 UE 5.8 Python API
以下 Send2UE 用到的 UE API 需在 5.8 上确认未废弃/改名(静态读源码无法坐实,须实跑):
- `unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks()`
- `unreal.FbxImportUI`
- `unreal.EditorActorSubsystem.spawn_actor_from_object()`

---

## 一、整体架构(从"点击发送"到"资产出现在 UE")

```
send2ue()  [core/export.py:522]
  ├─ validations.ValidationManager.run()      校验
  ├─ create_asset_data(properties)            从 collection 收集 mesh/rig/hair
  │    └─ export_mesh() → export_file() → io.fbx.export()   写 FBX 到磁盘
  │       并把资产信息塞进 wm.send2ue.asset_data 字典
  └─ ingest.assets(properties)  [core/ingest.py]
       └─ UnrealRemoteCalls.import_asset()    跨进程调用 UE 导入
          └─ instance_asset()                 spawn 到关卡
```

**通信机制(两层)**:
1. **引导层** — `dependencies/remote_execution.py`(UE Python 插件自带的 Remote Execution 的 vendored 副本):UDP 多播 `239.0.0.1:6766` 发现运行中的编辑器,TCP `6776` 执行 Python 字符串。仅用于**发现编辑器 + 在 UE 内启动 XML-RPC 服务**。
2. **主力层** — `dependencies/rpc/*`:**XML-RPC over HTTP**(Blender 客户端 :9997 → UE 服务端 :9998)。用"代码投递"技巧:`inspect.getsource()` 抓函数源码 → 在 UE 端 `exec()` 执行。UE 端通过 `register_slate_post_tick_callback` 把调用 marshal 到主线程。

> **关键**: Send2UE **不用** UE 的 Remote Control 插件。它用 Python 插件的 Remote Execution 引导 + 自建 XML-RPC。

**UE 端导入**(`dependencies/unreal.py`):
- 导入 FBX: `UnrealRemoteCalls.import_asset()` → 构造 `unreal.FbxImportUI` → `AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])`
- spawn 到关卡: `instance_asset()` → `EditorActorSubsystem.spawn_actor_from_object()` + `set_actor_transform()`
- 材质: 无独立材质创建,靠 FBX 的 `import_materials`/`import_textures` 标志随网格一起导入

---

## 二、核心技术发现(直接影响决策)

### 1. FBX 缩放/轴向 —— 不能照抄参数值
Send2UE 的 FBX 导出默认参数(`resources/settings.json` transform 段):

| 参数 | 默认值 |
|------|--------|
| `global_scale` | **1.0** ← 注意不是 100 |
| `apply_scale_options` | `FBX_SCALE_NONE` |
| `axis_forward` | `Y` |
| `axis_up` | `Z` |
| `apply_unit_scale` | `true` |
| `bake_space_transform` | `false` |

**100 倍(米→厘米)不是靠 `global_scale`,而是靠 `core/io/fbx.py` 里 `SCALE_FACTOR=100` 手动注入**到 monkey-patch 的 FBX 写入函数中。所以精简版若用标准 `bpy.ops.export_scene.fbx`,缩放值必须**在 Phase 0(b) 实测确定**,不能直接抄 1.0。

### 2. monkey-patch 是"皇冠明珠"也是"最大负债"
`core/io/fbx.py` 猴补丁了 Blender 内部模块 `io_scene_fbx.export_fbx_bin` 的 4 个函数(`fbx_animations_do`/`fbx_data_armature_elements`/`fbx_data_object_elements`/`fbx_data_bindpose_element`),用于:
- 骨骼 bindpose / skin cluster 矩阵的 SCALE_FACTOR 修正
- 动画 location/scale 关键帧缩放
- 静态网格的 object-origin 居中(`use_object_origin`)
- armature 重命名为 'Armature'(UE 保留字处理)

**耦合风险**: 紧贴 Blender 内部 API,版本敏感(代码里已有 `bpy.app.version >= (4,0,0)` 的 `elem_data_single_char` 分支)。Blender 5.1 需重新验证。

**但对静态网格 MVP**: 猴补丁真正必要的只有"轴向转换 + 可选 origin 居中";armature/bindpose/动画缩放全部用不上。

---

## 三、fork vs 重写 决策

### 推荐: **分阶段混合策略**(不是二选一)

**Phase 1(静态网格 MVP)→ 精简自写,约 300-500 行**
- 理由: Send2UE 的 11000 行里,静态网格 MVP 用不到的占 ~90%(collection 工作流、LOD、socket、groom、ue2rigify、extension 系统、代码投递式 XML-RPC)。fork 后再裁剪 > 直接精简自写。
- 导出: 标准 `bpy.ops.export_scene.fbx`(缩放参数经 Phase 0(b) 实测确定)
- 通信: **只用 Remote Execution 层**——发一条固定的 Python 命令字符串给 UE 跑 `import_asset_tasks`,**不引入 XML-RPC 代码投递工厂**(大幅简化)
- 可直接复用(MIT,vendored): `dependencies/remote_execution.py`(本就是 UE 自带文件)

**Phase 2+(骨骼/动画)→ 采纳 Send2UE 的 `core/io/fbx.py`**
- bindpose/skin 的缩放数学很难重写且易错,直接复用猴补丁导出器(需在 Blender 5.1 上重新验证版本兼容)

**Phase 1.5(MCP 封装)→ 包住精简版的 export→import 核心逻辑**

---

## 四、风险清单

| 风险 | 等级 | 缓解 |
|------|------|------|
| 静态网格缩放正确性(global_scale 未知) | **高** | Phase 0(b) 用已知尺寸立方体实测,再定参数 |
| UE 5.8 Python API 可能改名/废弃(import_asset_tasks 等) | 中 | Phase 0(b) 实跑确认,见 §零待验证清单 |
| Remote Execution 需在 UE Python 插件里启用 | 低 | 插件已就位,启用 "Remote Execution" 选项即可;协议已核实与 5.8 一致 |
| 猴补丁对 Blender 5.1 版本敏感 | 中 | 4 个目标函数已确认存在(§零),但路径移到 addons_core 且未测过;Phase 2 采纳前实跑验证 |
| XML-RPC 代码投递过于复杂 | — | Phase 1 直接绕开,不用 |

---

## 五、Phase 0(b) 实测结果(2026-09-26,已在 UE 5.8 + Blender 5.1 实跑)

**全链路跑通,三大未知全部消除。**

### 实测环境
- Blender 5.1.0(默认 Cube,2.0×2.0×2.0 m,METRIC 单位 1 BU=1 m)
- UE 5.8.3(`D:\test`,已启用 PythonScriptPlugin + bRemoteExecution)
- 通道: Blender Python 加载 UE 自带 `remote_execution.py` → 多播发现 UE → TCP 命令

### 验证结论
| 验证项 | 结果 |
|--------|------|
| Remote Execution 多播发现 UE 节点 | ✅ 发现 node(engine_version 5.8.3, project test) |
| 命令通道 `open_command_connection` + `run_command` | ✅ success=True,回传 stdout |
| UE 5.8 Python API 可用性 | ✅ `import_asset_tasks`/`FbxImportUI`/`AssetImportTask`/`EditorActorSubsystem`/`spawn_actor_from_object` 全部存在 |
| **静态网格缩放(global_scale=1.0)** | ✅ **导入后网格包围盒 200×200×200 cm,精确正确** |
| 静态网格缩放(global_scale=100) | ❌ 导入无产出,`/Game/Phase0Test/CubeS100` 不存在 |

### 锁定的精简版 FBX 导出参数(静态网格,已实测正确)
```python
bpy.ops.export_scene.fbx(
    filepath=..., use_selection=True,
    global_scale=1.0,                 # ← 关键: 1.0,不是 100
    apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_NONE',
    axis_forward='Y', axis_up='Z',
    object_types={'MESH'},
    use_mesh_modifiers=True,
    bake_space_transform=False,
    mesh_smooth_type='OFF',
)
```
UE 端导入(约 20 行,无需 XML-RPC / 无需猴补丁):
```python
task = unreal.AssetImportTask(); task.filename=fbx; task.destination_path='/Game/...'
task.destination_name=name; task.automated=True; task.replace_existing=True; task.save=True
o = unreal.FbxImportUI(); o.import_mesh=True; o.import_as_skeletal=False
o.import_animations=False; o.import_materials=False; o.import_textures=False
task.options=o
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actor = eas.spawn_actor_from_object(sm, unreal.Vector(x,y,z))
```

### 对决策的影响
**强力印证"Phase 1 精简自写"路线**: 标准 FBX 导出(global_scale=1)+ 一条 `run_command` 固定 Python 命令,即可完成整个静态网格 MVP,**不需要 Send2UE 的 XML-RPC 代码投递,也不需要猴补丁**。Send2UE 的猴补丁价值集中在骨骼/动画(Phase 2 再采纳)。

### 尚未验证(留到 Phase 1)
- **朝向/手性**: 测试用的是对称立方体,无法区分镜像/翻转。Phase 1 需用**非对称网格**验证 axis_forward=Y/axis_up=Z 不产生镜像。
- 多网格、含修改器、含 UV、非均匀缩放的边界用例。

### 实测遗留物(可清理)
- UE 资产: `/Game/Phase0Test/CubeS1`(StaticMesh)
- UE 关卡: spawn 了一个 CubeS1 actor(位于当前打开的关卡)
- 磁盘: `phase0_test/cube_s1.fbx`、`cube_s100.fbx`
- 配置改动: `D:\test\test.uproject`(+PythonScriptPlugin)、`D:\test\Config\DefaultEngine.ini`(+Remote Execution 段)

---

## 六、下一步

Phase 0 完成,决策明确 → **进入 Phase 1:精简自写静态网格 MVP addon**。
首个动作建议: 搭 Blender 端 addon 骨架(N-panel + 导出算子,用上面锁定的参数),再做 UE 端导入命令,最后用非对称网格验证朝向。

---

## 七、Phase 1 实测结果(2026-09-26,静态网格 MVP addon 全链路跑通)

**addon `blender_ue_bridge.py` 已在 UE 5.8.3 + Blender 5.1 实跑通过,含朝向定论。**

### 端到端(默认 Cube)
- `bpy.ops.ue_bridge.connect()` → 发现并连接 UE 节点(test | 5.8.3)
- `bpy.ops.ue_bridge.send_selected()` → 导出 FBX 到 `_stage/ue_bridge/cube.fbx` → UE 导入 → 生成 actor
- 结果:`SM_Cube: ok size_cm=[200,200,200] spawned`(2m 立方体精确变 200cm)

### 朝向/手性(非对称 L 形块,补 Phase 0 缺口)
用 X 方向也非对称的 L 形块(Blender 局部包围盒 min(-50,-100,0) max(150,0,200) cm),
排除"只翻 Y"(正确手性转换)与"X、Y 都翻"(错误镜像)给出相同包围盒的歧义。

| 轴 | Blender (cm) | UE (cm) | 映射 |
|---|---|---|---|
| X | [-50, 150] | [-50, 150] | X→X,**未翻转** |
| Y | [-100, 0] | [0, 100] | Y→-Y,翻转(右手系→左手系必需) |
| Z | [0, 200] | [0, 200] | Z→Z,未翻转,物体正立 |

**结论:恰好单轴翻转(Y),行列式变号 = 正确的右手系→左手系转换,网格无镜像,UE 外观与 Blender 一致。** UE 包围盒与期望值逐位一致。

### connect 故障排查(已解决)
首次 `connect()` 报 `Remote party failed to attempt the command socket connection!`。
根因:Phase 0(b) 手动测试遗留的 `_ue_rx` RemoteExecution 对象仍存活于 qoder_bridge 常驻命名空间,占用命令端口 6776,与 addon 新建实例冲突。
解决:停掉遗留对象后重连即成功。addon 自身 `connect()` 已先 `disconnect()` 自己的实例,无需额外加固(一次性外部干扰)。

### Phase 1 遗留物(测试资产,按需保留)
- UE 资产:`/Game/BridgeImport/SM_Cube`、`/Game/BridgeImport/SM_LBlock`
- UE 关卡:上述网格各 spawn 了 actor(LBlock 因重建发送了两次,有 2 个)
- 磁盘:`%TEMP%/blender_ue_bridge/_stage/ue_bridge/{cube,lblock}.fbx`
