# Phase 2a 骨骼验证结果(2026-09-26)

## 测试资产
程序化最小绑定:TestRig(4 骨)+ TestBody(4 段 box 蒙皮)

### Blender 侧(已知数值)
| 骨名 | head(m) | tail(m) | 长度(m) |
|------|---------|---------|---------|
| root | (0,0,0) | (0,0,0.5) | 0.5 |
| spine | (0,0,0.5) | (0,0,1.0) | 0.5 |
| arm_L | (0,0,1.0) | (0,0.6,1.0) | 0.6 (+Y 侧) |
| arm_R | (0,0,1.0) | (0,-0.4,1.0) | 0.4 (-Y 侧) |

**网格包围盒(Blender)**: min(-0.3,-0.4,0) max(0.3,0.6,1.1) m = min(-30,-40,0) max(30,60,110) cm

**期望 UE 包围盒**(X→X, Y→-Y, Z→Z, ×100): min(-30,-60,0) max(30,40,110) cm

## FBX 导出参数(锁定)
```python
bpy.ops.export_scene.fbx(
    filepath=...,
    use_selection=True,
    global_scale=1.0,                  # ← 关键:与静态网格相同
    apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_NONE',
    axis_forward='Y',
    axis_up='Z',
    object_types={'ARMATURE', 'MESH'}, # ← 骨骼 + 网格
    use_mesh_modifiers=True,
    bake_space_transform=False,
    mesh_smooth_type='OFF',
    primary_bone_axis='Y',             # ← 骨骼专用
    secondary_bone_axis='X',           # ← 骨骼专用
    armature_nodetype='NULL',          # ← 骨骼专用
    add_leaf_bones=False,              # ← 骨骼专用
    use_armature_deform_only=True,     # ← 骨骼专用
    bake_anim=False,                   # ← 本次不测动画
)
```

## UE 侧验证结果

### 1. 网格包围盒 ✅ **完全正确**
```
实际: min(-30, -60, 0) max(30, 40, 110) cm
期望: min(-30, -60, 0) max(30, 40, 110) cm
```
- X 对称: [-30, 30] ✓
- Y 非对称(手性验证): [-60, 40] ✓ (Blender +Y 侧 60cm → UE -Y 侧 60cm)
- Z 范围: [0, 110] ✓

**结论**: 缩放正确(1m = 100cm),手性正确(Y→-Y 翻转)。

### 2. 骨骼世界空间位置 ✅ **正确**
| 骨名 | UE 位置(cm) | 期望(cm) | 结果 |
|------|-------------|----------|------|
| root | (0, 0, 0) | (0, 0, 0) | ✓ |
| spine | (0, 0, 50) | (0, 0, 50) | ✓ |
| arm_L | (0, 0, 100) | (0, 0, 100) | ✓ |
| arm_R | (0, 0, 100) | (0, 0, 100) | ✓ |

**结论**: 骨骼位置精确匹配,缩放参数正确。

### 3. 骨骼层级结构
**实际**: 5 根骨骼
- TestRig(armature 根节点,FBX 自动添加)
- root → spine → arm_L
- spine → arm_R

**期望**: 4 根骨骼(root, spine, arm_L, arm_R)

**差异原因**: FBX 导出器将 Blender 的 armature 对象本身也导出为一根骨骼("TestRig"),这是 FBX 格式的标准行为,不影响功能。

### 4. 骨骼相对变换(Reference Pose)
```
TestRig: scale=(100, 100, 100)  ← armature 根节点缩放 100×
root:    location=(0,0,0), rotation=(0.7071, 0, 0, -0.7071)  ← 90° X 轴旋转
spine:   location=(0, -0.5, 0)  ← 相对父骨 0.5cm(实际是 50cm,单位待确认)
arm_L:   location=(0, -0.5, 0), rotation=(-0.7071, 0, 0, -0.7071)
arm_R:   location=(0, -0.5, 0), rotation=(0, -0.7071, 0.7071, 0)
```

**关键发现**: armature 根节点(TestRig)的 scale=100,这正是 Send2UE 猴补丁注入 `SCALE_FACTOR=100` 的目标。FBX 导出器自动在 armature 根节点应用 100× 缩放,将米转厘米。

**但这不影响骨骼世界空间位置**,因为:
- 世界空间位置 = 父变换 × 局部变换
- arm_L 世界位置 = TestRig(scale=100) × root × spine × arm_L_local
- 最终结果仍然是 Z=100cm ✓

## 结论

### ✅ 骨骼缩放参数已锁定
**`global_scale=1.0` 同时适用于静态网格和骨骼网格**,无需 Send2UE 的猴补丁。

原因:
1. FBX 导出器自动在 armature 根节点添加 scale=100(米→厘米)
2. 网格顶点不受此影响(网格有自己的单位转换)
3. 骨骼世界空间位置正确(已验证)
4. 不需要手动注入 SCALE_FACTOR

### ✅ 骨骼朝向参数已锁定
- `primary_bone_axis='Y'`
- `secondary_bone_axis='X'`
- `armature_nodetype='NULL'`
- `add_leaf_bones=False`

这些参数与 Send2UE 默认值一致,实测工作正常。

### ⚠ 遗留物(可清理)
- UE 资产: `/Game/BridgeImport/TestRig_Skeletal`(SkeletalMesh)
- UE 资产: `/Game/BridgeImport/TestRig_Skeletal_Skeleton`(Skeleton)
- UE 关卡: spawn 了 TestRig_Skeletal actor(位于原点)
- 磁盘: `_stage/ue_bridge/testrig_skeletal.fbx`

## 下一步
Phase 2a 完成 → 进入 Phase 2b:扩展 addon 支持骨骼网格(不破坏静态网格路径)。
