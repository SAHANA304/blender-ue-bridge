# 项目上下文 · Blender→UE 桥接插件

> 新项目启动清单。压缩恢复后先读本文件 + `IMPLEMENTATION_PLAN.md`。

## 项目目标
开发一个 Blender 桥接 UE 的插件,首期做**静态网格 MVP**,采用 **FBX + MCP 混合路线**。

## 已确认决策(2026-09-26)
- 技术路线: FBX 主传输 + MCP 封装(可在 Qoder 里 AI 驱动)
- 开发策略: **先研究官方 Send to Unreal 源码,再决定 fork 还是从零重写**(Phase 0 结束才定)
- 首期范围: 静态网格一键导出导入 + 自动放置到关卡

## 关键环境路径(已实测)
- Blender 5.1.0(build 2026-03-17): `D:\blender\blender.exe`
- Blender FBX 模块: `D:\blender\5.1\scripts\addons_core\io_scene_fbx\`(注意在 **addons_core**,非 addons)
- Blender 插件目录: `%APPDATA%\Blender Foundation\Blender\5.1\scripts\addons`
- UE 5.8 引擎: `D:\ue\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe`
- UE 测试项目: `D:\test`(Automation_test)
- UE Python 插件 + Remote Control 插件: 均已就位
- UE 自带 remote_execution.py: `D:\ue\UE_5.8\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python\remote_execution.py`

## 版本兼容性核实结论(2026-09-26,详见 PHASE0_ANALYSIS.md §零)
- **UE 5.8**: Remote Execution 协议与 Send2UE vendored 副本**完全一致**(v1 / 'ue_py' / 6766 / 6776)→ 可直接用 UE 5.8 自带那份
- **Blender 5.1**: Send2UE 猴补丁的 4 个 FBX 函数**全部还在**,但模块移到 addons_core、且官方未在 5.1 测过 → 结构兼容,采纳前须实跑验证
- Send2UE 克隆版本 = **2.4.3**(网传"2.6.5 支持 5.1"对不上源码)
- 待 Phase 0(b) 运行时确认的 UE API: `import_asset_tasks` / `FbxImportUI` / `spawn_actor_from_object`

## 相关 Skills(本项目会用到)
- `blender-addon-ux` — Blender 插件开发规范(图标兼容、面板 draw 异常)
- `plugin-ux-principles` — 跨 DCC 插件 UX 通识
- `dcc-transform-export-import` — 导出导入的坐标轴/变换问题(本项目核心难点)
- `persist-plans` / `task-shelf-resume` — 计划持久化与任务搁置恢复

## 用户历史教训(务必遵守)
- Blender 5.1: 无效图标名会导致面板 draw **静默崩溃**,只用确认存在的图标
- Blender 5.1: EnumProperty 的 items **必须用英文**(中文乱码)
- 修改 addon 源文件后**立即 cp 到 Blender addons 目录**,否则看不到变化
- bmesh 操作前必须 `mesh.update()`
- 本机**无 node.exe**,JS 语法检查用 browser-use 的 file:// 页面
- 讨论 3D 能力时**不要低估**截图/渲染的视觉检查能力
- 沟通用**纯中文**

## 参考项目(真实仓库,版本以克隆后源码为准)
- `EpicGames/BlenderTools` — 官方 Send to Unreal(最佳架构范本)
- `unreal-datasmith/bl_datasmith` — Datasmith 导出,材质映射参考
- `xavier150/Blender-For-UnrealEngine-Addons` — 批量导出 + UE 脚本生成
- `Befzz/blender3d_import_psk_psa` — PSK/PSA 骨骼动画格式

## 当前状态
**Phase 1.5 完成**(2026-09-26,MCP 封装 + AI 驱动桥接)。

Phase 1.5 结论:
- **bridge_api.py 已创建**:独立 MCP API 层,提供 `connect()` / `disconnect()` / `status()` / `send_selected()` 四个函数
- **全链路 MCP 测试通过**:
  - `bridge_api.status()` → 返回场景物体列表 + 连接状态
  - `bridge_api.connect()` → `{"ok": True, "info": "test | 5.8.3-58210709+++UE5+Release-5.8"}`
  - `bridge_api.send_selected()` → Cube 导出 FBX → UE 导入 `SM_Cube` 200x200x200 cm + spawn
  - `bridge_api.disconnect()` → `{"ok": True}`
- **AI 调用方式**:通过 Blender MCP `execute_py` 执行 `import bridge_api; bridge_api.send_selected()`
- 详见 `PHASE1_5_MCP_API.md`

Phase 3 全部完成(2026-09-26,动画导出验证 + addon 扩展)。

Phase 3 结论:
- **动画 FBX 导出成功**:TestRig + TestBody + Act_wave(20 帧)+ Act_nod(9 帧)导出为 `testrig_anim.fbx`(83KB)
- **锁定动画 FBX 参数**:`bake_anim=True`, `bake_anim_use_all_bones=True`, `bake_anim_force_startend_keying=True`, `bake_anim_step=1.0`, `bake_anim_simplify_factor=0.0`
- **UE 连接已恢复**:UDP 6766 多播发现正常,TCP 命令通道可用
- **UE 动画导入成功**:FBX 导入生成 SkeletalMesh + Skeleton + 2 个 AnimSequence
  - `/Game/BridgeImport/SK_TestRig_v2TestRig_Act_nod` → AnimSequence (0.3 秒, 9 帧, 30 FPS)
  - `/Game/BridgeImport/SK_TestRig_v2TestRig_Act_wave` → AnimSequence (0.633 秒, 20 帧, ~31.6 FPS)
- **addon v0.3.0 已更新**:
  - `FBX_SKELETAL_EXPORT_PARAMS` 添加动画导出参数
  - `_UE_SKELETAL_IMPORT_SCRIPT` 启用 `import_animations = True`
  - 结果解析添加 AnimSequence 信息(路径 + 时长)
  - 已同步到 Blender addons 目录

Phase 2b 完成(2026-09-26,addon 已扩展支持骨骼网格)。

Phase 0 结论(仍有效):
- 全链路跑通:Blender→多播发现 UE→TCP 命令→UE Python 导入 FBX+spawn
- **静态网格缩放锁定: `global_scale=1.0`**(2m cube → UE 里精确 200cm);global_scale=100 导入失败
- UE 5.8 关键 API 全部可用;Remote Execution 协议兼容
- 决策定案: **精简自写**(标准 FBX 导出 + 一条 run_command,不用 XML-RPC/不用猴补丁)
- 详见 `PHASE0_ANALYSIS.md` §五

Phase 1 新增结论:
- addon 已同步到 addons 目录并启用;`ue_bridge.connect` / `ue_bridge.send_selected` 实跑通过
- 默认 Cube:`SM_Cube size_cm=[200,200,200] spawned`
- **朝向/手性定论**(非对称 L 形块):恰好单轴翻转(Y),正确右手系→左手系转换,无镜像

Phase 2a 新增结论(骨骼网格验证):
- **骨骼缩放参数锁定**: `global_scale=1.0` 同时适用于静态网格和骨骼网格,**不需要 Send2UE 的猴补丁**
- 原因: FBX 导出器自动在 armature 根节点添加 scale=100(米→厘米),骨骼世界空间位置正确
- 骨骼朝向参数锁定: `primary_bone_axis='Y'`, `secondary_bone_axis='X'`, `armature_nodetype='NULL'`, `add_leaf_bones=False`
- 网格包围盒完全正确: min(-30,-60,0) max(30,40,110) cm(手性验证通过,Y→-Y 翻转)
- 骨骼世界空间位置正确: spine at Z=50cm, arm_L/R at Z=100cm
- 详见 `PHASE2A_RESULTS.md`

**UE 连接问题临时解决方案**(2026-09-26):
- 问题:TCP 6776 命令端口 CLOSE_WAIT,`open_command_connection` 报 "Remote party failed to attempt the command socket connection"
- 原因:之前测试残留的连接状态未正确清理
- 解决:在 UE Python 控制台执行 `import unreal; unreal.PythonScriptPlugin.reload_scripts()`,或在 Edit → Plugins 里禁用/启用 Python Script Plugin
- 备选:手动在 UE 执行 `ue_import_anim.py` 脚本(已准备好)

**下一步**:见当前状态章节。

Phase 2b 新增结论(addon 扩展):
- addon v0.2.0 已支持骨骼网格导出,不破坏静态网格路径
- 智能检测:选区含 armature → 骨骼路径;仅 mesh → 静态路径;混合选区 → 分别处理
- 骨骼网格 UE 导入用 `SK_` 前缀(UE 命名约定)
- 实测:TestRig(骨骼)+ LBlock(静态)混合选区 → 1 skeletal + 1 static 正确导入

**下一步**:首期 MVP 全部完成(静态网格 + 骨骼网格 + 动画 + MCP 封装)。后续可扩展:批量导出、材质支持、LOD 等。

## 实测遗留物(测试资产,按需保留)
- Phase 0(b): UE `/Game/Phase0Test/CubeS1` + spawn actor;磁盘 `phase0_test/cube_s1.fbx`、`cube_s100.fbx`
- Phase 1: UE `/Game/BridgeImport/SM_Cube`、`SM_LBlock` + 关卡 spawn actor(LBlock 有 2 个);磁盘 `%TEMP%/blender_ue_bridge/_stage/ue_bridge/{cube,lblock}.fbx`
- Phase 2a: UE `/Game/BridgeImport/TestRig_Skeletal`(SkeletalMesh)、`TestRig_Skeletal_Skeleton`(Skeleton)+ spawn actor;磁盘 `_stage/ue_bridge/testrig_skeletal.fbx`
- 配置: `D:\test\test.uproject` 和 `DefaultEngine.ini` 的改动(后续阶段还要用,暂留)
