# 任务搁置总结

**搁置时间**: 2026-09-26
**任务名称**: Blender→UE Bridge 插件开发(MVP 完成，待压力测试)
**搁置原因**: 用户将新开窗口，用复杂角色模型进行压力测试
**交接记录**: `HANDOFF_RECORD.md` — 已整理交接消息 + 目标窗口确认状态
**目标窗口**: `39c328f9-47ac-4c0d-94d1-96d98607f1c0` — 环境已确认就绪，等待用户提供角色模型

## 需求回顾

开发一个 Blender 桥接 UE 的插件，支持一键将静态网格、骨骼网格、动画从 Blender 发送到 Unreal Engine 5.8。采用 FBX + MCP 混合路线，AI 可通过 MCP 驱动。

## 当前实现状态

### 已完成(6 个 Phase 全部完成)

- **Phase 0**: 源码分析 + 环境验证 — 确认 UE 5.8 Remote Execution 协议兼容，Blender 5.1 FBX 模块结构兼容
- **Phase 1**: 静态网格 MVP — Cube 200x200x200cm 精确导入 UE，朝向/手性验证通过
- **Phase 2a**: 骨骼网格验证 — `global_scale=1.0` 同时适用静态和骨骼，不需要猴补丁
- **Phase 2b**: addon 扩展支持骨骼 — 智能检测选区类型，分别走静态/骨骼路径
- **Phase 3**: 动画导出 — `bake_anim=True` + 5 个锁定参数，UE 生成 AnimSequence
- **Phase 1.5**: MCP 封装 — `bridge_api.py` 提供 JSON 返回值 API，通过 `execute_py` 调用

### 待完成

- **复杂角色压力测试**(用户计划在新窗口执行)
  - 多骨骼 + 多蒙皮网格导出稳定性
  - 多 Action 同时导出的 AnimSequence 生成
  - 大文件 FBX 导出耗时
  - UE 导入后骨骼/动画完整性

### 已知但未处理的问题

1. 动画 FPS 微偏: Act_wave 20帧 → 31.58 FPS(目标 30)，可接受
2. UE TCP 命令端口长时间不操作可能 CLOSE_WAIT，需 `unreal.PythonScriptPlugin.reload_scripts()` 恢复
3. replace_existing 首次导入可能不生成动画资产，改名重新导入可解决

## 技术经验与踩坑记录

### 关键发现

1. **缩放不需要猴补丁**: `global_scale=1.0` 即可，FBX 导出器自动在 armature 根节点加 scale=100(m→cm)
2. **骨骼轴参数**: `primary_bone_axis='Y'`, `secondary_bone_axis='X'`, `armature_nodetype='NULL'`, `add_leaf_bones=False`
3. **UE FbxAnimSequenceImportData API 有限**: 无 `animation_length` / `import_bone_tracks` 可设
4. **Blender 5.1 layered action 系统**: 替代了旧的 `Action.fcurves`，导出时 FBX exporter 自动处理

### 踩坑记录

1. **UE 连接残留**: TCP 6776 CLOSE_WAIT → 在 UE Python 控制台执行 reload_scripts() 或禁用/启用 Python Script Plugin
2. **首次导入动画不生成 AnimSequence**: 可能是 replace_existing 缓存问题，换个资产名(如加 `_v2`)重新导入即可
3. **Unicode 编码**: Windows GBK 环境下 Python 脚本不能用 ✓✗ 等 Unicode 字符，会报 `'gbk' codec can't encode character`
4. **Blender MCP 连接**: 需要在 Blender 里启用 Qoder Bridge addon，否则 127.0.0.1:8766 无响应

### 环境路径

- Blender 5.1: `D:\blender\blender.exe`
- UE 5.8: `D:\ue\UE_5.8\`
- UE 测试项目: `D:\test\`
- remote_execution.py: `D:\ue\UE_5.8\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python\`
- Blender addons: `%APPDATA%\Blender Foundation\Blender\5.1\scripts\addons\`

## 恢复时的检查清单

- [ ] 确认 Blender 里 **Qoder Bridge** addon 已启用(MCP 连接)
- [ ] 确认 Blender 里 **Blender UE Bridge** addon 已启用
- [ ] 确认 UE 已开启 **Remote Execution** + **Python Script Plugin**
- [ ] 如果 TCP 命令端口异常，在 UE Python 控制台执行 `unreal.PythonScriptPlugin.reload_scripts()`
- [ ] 读取 `REPORT_SUMMARY.md` 了解完整技术结论
- [ ] GitHub 仓库: https://github.com/SAHANA304/blender-ue-bridge

## 关键文件清单

| 文件 | 作用 | 状态 |
|------|------|------|
| `addon/blender_ue_bridge.py` | addon 主体 v0.3.0(UI 面板 + FBX 导出 + UE 导入) | 完成 |
| `addon/bridge_api.py` | MCP API 层(JSON 返回值，AI 驱动) | 完成 |
| `_PROJECT_CONTEXT.md` | 项目上下文 + 所有 Phase 结论 | 完成 |
| `REPORT_SUMMARY.md` | 阶段性总结报告 | 完成 |
| `PHASE0_ANALYSIS.md` | Phase 0 分析报告 | 完成 |
| `PHASE1_5_MCP_API.md` | MCP API 文档 + 调用示例 | 完成 |
| `PHASE2A_RESULTS.md` | 骨骼网格验证结果 | 完成 |
| `PHASE3_RESULTS.md` | 动画导出验证结果 | 完成 |

## GitHub

仓库: https://github.com/SAHANA304/blender-ue-bridge
分支: master
最新 commit: `3710582` — Phase 0-3 + Phase 1.5: Blender→UE Bridge MVP complete
