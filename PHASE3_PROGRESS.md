# Phase 3 进展报告 · 动画导出验证

> 日期: 2026-09-26  
> 状态: 进行中 - 遇到动画导入问题

## 已完成

### 1. 动画 FBX 导出 ✓
- **导出文件**: `testrig_anim.fbx` (83KB)
- **测试资产**: TestRig (armature) + TestBody (mesh) + Act_wave (action, 20 帧)
- **导出参数**:
  ```python
  bake_anim=True
  bake_anim_use_all_bones=True
  bake_anim_force_startend_keying=True
  bake_anim_step=1.0
  bake_anim_simplify_factor=0.0
  ```
- **导出时间**: 0.038 秒

### 2. UE Remote Execution 连接 ✓
- **UDP 6766 多播发现**: 正常
- **TCP 命令通道**: 可用 (用户手动重载 Python Script Plugin 后恢复)
- **测试命令**: `print("Hello from UE!")` 执行成功

### 3. FBX 导入到 UE ✓ (部分)
- **SkeletalMesh**: `/Game/BridgeImport/SK_TestRig` ✓
- **Skeleton**: `/Game/BridgeImport/SK_TestRig_Skeleton` ✓
- **AnimSequence**: ❌ **未生成**

## 当前问题

### 问题描述
FBX 文件导入 UE 后只生成了 SkeletalMesh 和 Skeleton，没有生成 AnimSequence。

### 已尝试
1. 使用 `FbxImportUI` 配置:
   - `import_mesh = True`
   - `import_as_skeletal = True`
   - `import_animations = True`
   - `import_materials = False`
   - `import_textures = False`

2. 检查 `FbxAnimSequenceImportData` 属性:
   - 发现 UE 5.8 的 API 与文档不一致
   - `animation_length` 属性不存在
   - `import_bone_tracks` 属性不存在

### 待排查方向

#### 方向 1: FBX 文件本身问题
- 验证 FBX 文件是否真的包含动画数据
- 用其他工具(如 UE 手动导入)测试同一个 FBX 文件
- 重新导出 FBX，确保动画数据被正确写入

#### 方向 2: UE 导入配置问题
- 检查是否需要设置 `skeletal_mesh_import_data` 的特定属性
- 检查是否需要单独的动画导入任务
- 查看 UE 日志中是否有动画相关的警告或错误

#### 方向 3: Blender 5.1 FBX 导出器问题
- Blender 5.1 的 layered action 系统可能与 FBX 导出器不兼容
- 检查是否需要将 action 转换为旧格式再导出
- 验证 `bake_anim` 参数是否真的生效

## 下一步

1. **验证 FBX 文件**: 在 UE 编辑器中手动导入 `testrig_anim.fbx`，看是否能导入动画
2. **检查 UE 日志**: 查看导入过程中的详细日志
3. **重新导出 FBX**: 在 Blender 中重新导出，确保动画数据正确
4. **测试其他工具**: 用 Maya 或 3ds Max 导出测试 FBX，验证 UE 动画导入功能

## 测试脚本

### Blender 重新导出脚本
文件: `reexport_anim.py`
用途: 在 Blender 中重新导出动画 FBX，验证导出参数

### UE 导入脚本
文件: `import_anim_simple.py`
用途: 通过 Remote Execution 导入动画 FBX 到 UE

### UE API 检查脚本
文件: `check_ue_anim_import.py`, `check_skeletal_data.py`
用途: 检查 UE 5.8 的动画导入 API 可用性

## UE 日志摘要

```
LogInterchangeEngine: Display: Interchange start importing source [testrig_anim.fbx]
LogSkeletalMesh: Built Skeletal Mesh [0.01s] /Game/BridgeImport/SK_TestRig
LogInterchangeImport: Imported (FBXSDK) of testrig_anim.fbx in [0 min 0.121 s]
```

**注意**: 日志中没有提到动画导入，只有 SkeletalMesh。

## 环境信息

- Blender: 5.1.0 (build 2026-03-17)
- UE: 5.8.3 (CL-58210709)
- Python: 3.11.8 (UE 内置)
- 操作系统: Windows 11 (24H2)
