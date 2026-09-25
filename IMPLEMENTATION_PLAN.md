# Blender → UE 桥接插件 · 实现计划

> 生成日期: 2026-09-26
> 决策已确认: **FBX + MCP 混合路线** / **先研究源码再决定 fork 还是重写** / **首期做静态网格 MVP**

---

## 一、环境(已实测核实)

| 组件 | 路径 / 状态 |
|------|------------|
| Blender 5.1 | `D:\blender\blender.exe` |
| Blender 用户插件目录 | `%APPDATA%\Blender Foundation\Blender\5.1\scripts\addons`(已有 `qoder_bridge.py`、`plasticity-blender-addon-gamedev`) |
| UE 5.8 引擎 | `D:\ue\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe` |
| UE Python 插件 | `Engine\Plugins\Experimental\PythonScriptPlugin` ✅ 已就位 |
| UE Remote Control | `Engine\Plugins\VirtualProduction\RemoteControl`(+ WebInterface)✅ 已就位 |
| UE 测试项目 | `D:\test`(Automation_test,C++ 项目) |
| 项目工作目录 | `C:\Users\HASEE\Documents\Qoder\2026-09-26\9d8c180f`(空,全新) |

**结论**: FBX+MCP 混合路线所需的两大 UE 端前提(Python 插件、Remote Control)均已存在,底座可通。

---

## 二、目标架构

```
┌────────────────────┐   FBX + JSON manifest   ┌──────────────────┐
│  Blender 5.1 addon  │ ──────────────────────> │   共享/临时目录    │
│  (N-panel + 算子)   │                          └────────┬─────────┘
└─────────┬──────────┘                                   │
          │ HTTP / MCP 触发                               │ 读取 manifest
          ▼                                               ▼
┌────────────────────┐   Remote Control API    ┌──────────────────┐
│  MCP Tool (Qoder)   │ ─────────────────────> │  UE Python 脚本    │
│  AI 驱动整条链路     │      (端口 30010)       │  AssetTools 导入   │
└────────────────────┘                         │  + spawn 到关卡    │
                                                └──────────────────┘
```

- **数据主路径**: FBX(兼容性最好,风险最低)
- **控制路径**: HTTP + JSON,走 UE Remote Control API
- **自动化层**: 把核心逻辑封装为 MCP Tool,复用现有 blender MCP 生态

---

## 三、Phase 0 — 源码研究 + 环境验证(决策阶段,约 3-5 天)

**目标**: 读懂官方实现,产出"fork Send to Unreal vs 从零重写"的决策依据。

- [ ] 克隆 `EpicGames/BlenderTools`,重点读 `send2ue/` 目录:
  - 资产提取逻辑、FBX 导出参数配置
  - UE 端导入触发方式(文件系统?RPC?)
  - 坐标系 / 单位缩放转换的具体实现
- [ ] 读 `unreal-datasmith/bl_datasmith` 的材质映射逻辑(为 Phase 3 铺垫)
- [ ] **UE 端验证**: 在 `D:\test` 启用 Python + Remote Control 插件,手动跑通一次"Python 脚本导入一个 FBX 并 spawn 到关卡"
- [ ] **Blender 端验证**: 写最小 addon,导出选中网格为 FBX(验证坐标/缩放参数)
- [ ] **产出**: 决策文档(fork / 重写)+ MCP 封装切入点分析

**决策门槛**: Phase 0 结束后再定 Phase 1 是 fork 还是重写。

---

## 四、Phase 1 — 静态网格 MVP(FBX 主路径,约 2-3 周)

**里程碑**: Blender 里选中一个网格 → 一键 → 正确出现在 UE `D:\test` 关卡中(坐标、缩放、朝向都对)。

- [ ] **1.1 Blender 端 addon 骨架**
  - `bl_info` + N-panel 侧栏面板注册
  - ⚠️ 只用确认存在的图标名(Blender 5.1 无效图标会导致 draw 静默崩溃)
  - ⚠️ EnumProperty 的 items 用英文(中文在 Windows Blender 会乱码)
- [ ] **1.2 FBX 导出算子**
  - `bpy.ops.export_scene.fbx()`,关键参数:
    - `apply_unit_scale=True`,`global_scale=100`(米 → 厘米)
    - `axis_forward` / `axis_up` 处理 Z-up 右手 → 左手(Y 翻转)
    - `use_selection=True`
  - 自动重命名为 UE 约定(`SM_` 前缀)
- [ ] **1.3 JSON manifest 写入**
  - 记录: 资产名、FBX 路径、目标 UE Content 路径、变换矩阵
- [ ] **1.4 通信层**
  - 首选: HTTP 触发 UE Remote Control(端口 30010)
  - 备选: 纯文件监听(UE 端 Python 轮询目录)
- [ ] **1.5 UE 端导入脚本**
  - `unreal.AssetTools.import_asset_tasks()` + `unreal.FbxImportUI`
  - 导入到指定 Content 路径,spawn 到当前关卡
- [ ] **1.6 端到端测试**
  - 导出 cube → 验证 UE 里位置/缩放/朝向正确
  - 边界用例: 多网格、含修改器、含 UV、含非均匀缩放

---

## 五、Phase 1.5 — MCP 封装(约 1-2 周)

**目标**: 在 Qoder 里用自然语言 / MCP 驱动"把选中网格发到 UE"。

- [ ] 把 Phase 1 的 export→import 核心逻辑封装为 MCP Tool
- [ ] 复用现有 blender MCP(`mcp__blender__eval_py` 等)
- [ ] 设计工具接口: `send_static_mesh_to_ue(asset_names, ue_target_path)`
- [ ] 验证与现有 MCP 生态不冲突

---

## 六、后续 Phase(MVP 跑通后再评估)

- **Phase 2**: 骨骼网格 + 动画(NLA / Actions)传输
- **Phase 3**: PBR 材质自动重建(参考 bl_datasmith 的 Principled BSDF → UE 材质映射)
- **Phase 4**: 场景层级同步 + Live Link 实时预览

---

## 七、关键技术风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| 坐标系 / 缩放转换出错(镜像、缩小 100 倍) | 低 | 已有成熟方案,Phase 0 先单独验证 |
| UE 5.8 Remote Control 具体端点与旧文档不符 | 中 | Phase 0 用 `GET /remote/info` 实测端点清单 |
| MCP 封装与现有 blender MCP 协同冲突 | 中 | Phase 1.5 前先确认调用边界 |
| Send to Unreal 版本号 / "支持 Blender 5.1+UE5.6" 说法未经证实 | 中 | Phase 0 克隆后以实际源码为准 |

---

## 八、立即可做的第一步(Phase 0)

二选一启动:
- **(a)** 克隆 Send to Unreal 源码并分析架构(偏研究 fork/重写决策)
- **(b)** 先在 `D:\test` 里验证"UE Python 导入 FBX 并 spawn"能跑通(偏验证底座)
