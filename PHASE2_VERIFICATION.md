# Phase 2 骨骼/动画验证计划

## 目标
验证 Blender→UE 骨骼网格 + 动画链路,并**实测锁定骨骼专用 FBX 参数**(缩放/朝向/骨轴),
这是静态网格参数(global_scale=1.0)覆盖不到的新风险区。

## 为什么骨骼参数要重新实测
- 静态网格锁定的是 `global_scale=1.0` + `object_types={'MESH'}`。
- armature 的骨长、bind pose 在标准导出器下走**不同的缩放路径**,极易出 0.01×/100× 错。
  Send2UE 正是为此猴补丁注入 `SCALE_FACTOR=100`(见 reference/BlenderTools/send2ue/core/io/fbx.py)。
- `primary_bone_axis`/`secondary_bone_axis` 影响骨骼朝向,也是未知量。
- 结论:骨骼参数不能抄静态网格的,必须实测。

## 第一层测试资产:程序化最小绑定(Blender 内建,数值全部已知)

### 骨架 TestRig(单位:米)
| 骨名 | head | tail | 父骨 | 长度(m) |
|------|------|------|------|---------|
| root  | (0,0,0)   | (0,0,0.5)   | -     | 0.5 |
| spine | (0,0,0.5) | (0,0,1.0)   | root  | 0.5 |
| arm_L | (0,0,1.0) | (0,0.6,1.0) | spine | 0.6 (+Y 侧) |
| arm_R | (0,0,1.0) | (0,-0.4,1.0)| spine | 0.4 (-Y 侧) |

**非对称设计**:arm_L 长(0.6)且在 +Y,arm_R 短(0.4)且在 -Y。
用于测手性 —— 按静态网格已确定的映射(X→X, Y→-Y, Z→Z),
UE 里 arm_L 应落在 -Y 侧(长 60cm),arm_R 落在 +Y 侧(长 40cm)。

### 蒙皮网格 TestBody(4 段 box,每段绑一根骨)
- root  段: x[-0.3,0.3] y[-0.3,0.3] z[0,0.5]     → vg root
- spine 段: x[-0.3,0.3] y[-0.3,0.3] z[0.5,1.0]   → vg spine
- arm_L 段: x[-0.1,0.1] y[0,0.6]    z[0.9,1.1]   → vg arm_L
- arm_R 段: x[-0.1,0.1] y[-0.4,0]   z[0.9,1.1]   → vg arm_R

**Blender 局部包围盒**: min(-0.3,-0.4,0) max(0.3,0.6,1.1) m
= min(-30,-40,0) max(30,60,110) cm(Y 非对称,可同时验手性)

**期望 UE 包围盒**(X→X, Y→-Y, Z→Z,×100):
- min(-30, -60, 0)  max(30, 40, 110) cm

### 动画(2 个 action,已知关键帧,fps=30)
- `Act_wave`: arm_L rotation_euler Z 从 0(frame 1)→ 90°(frame 20)
- `Act_nod`:  spine rotation_euler X 从 0(frame 1)→ 30°(frame 10)

## 验证断言(UE 侧 Python,精确比对)
1. **导入类型**: 产物是 SkeletalMesh + Skeleton(不是 StaticMesh)。
2. **骨层级/命名**: 骨数=4,名字={root,spine,arm_L,arm_R},父子关系一致。
3. **缩放(核心)**: bind-pose 网格包围盒 == 期望值(上面),证明骨骼缩放参数正确。
4. **手性**: arm_L/arm_R 的 tip 落在期望的 ±Y 侧;或网格包围盒 Y 非对称方向正确。
5. **动画**: AnimSequence 存在,play_length / 帧数与 Blender 帧范围一致。

## 步骤
- Phase2a-1: 建程序化绑定(本文件规格),Blender 内自检数值。
- Phase2a-2: 候选骨骼 FBX 参数导出 + 手动 UE 导入命令(import_as_skeletal=True),跑断言。
- Phase2a-3: 若缩放/朝向错,调参数(global_scale / primary_bone_axis 等)重测,锁定正确组合。
- Phase2b: 参数锁定后,扩展 addon 支持骨骼分支(不破坏静态网格路径),再用绑定回归测试。

## 第二层(真实角色,待资产到位)
xcc 项目不在本地,暂不可用。到位后用它做 IK/面部骨/多动画的真实压测。
