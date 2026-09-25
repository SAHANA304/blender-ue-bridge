# Blender→UE Bridge 阶段性总结报告

> 2026-09-26 · SAHANA304 · Blender 5.1 + UE 5.8

---

## 一、项目成果

从零实现了一个 **Blender→Unreal Engine 桥接插件**，支持一键将静态网格、骨骼网格、动画从 Blender 发送到 UE，并可通过 AI (MCP) 驱动。

**GitHub 仓库**: https://github.com/SAHANA304/blender-ue-bridge

---

## 二、完成阶段

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 0 | 源码分析 + 环境验证 | 完成 |
| Phase 1 | 静态网格 MVP | 完成 |
| Phase 2a | 骨骼网格验证 | 完成 |
| Phase 2b | addon 扩展支持骨骼 | 完成 |
| Phase 3 | 动画导出 + UE 导入 | 完成 |
| Phase 1.5 | MCP 封装(AI 驱动) | 完成 |

---

## 三、技术结论(已锁定)

### FBX 导出参数

**静态网格**:
```python
global_scale=1.0, apply_scale_options='FBX_SCALE_NONE'
axis_forward='Y', axis_up='Z'
```

**骨骼网格**(在静态基础上追加):
```python
primary_bone_axis='Y', secondary_bone_axis='X'
armature_nodetype='NULL', add_leaf_bones=False
```

**动画**(在骨骼基础上追加):
```python
bake_anim=True, bake_anim_use_all_bones=True
bake_anim_force_startend_keying=True
bake_anim_step=1.0, bake_anim_simplify_factor=0.0
```

### 关键发现

1. **缩放**: `global_scale=1.0` 同时适用于静态和骨骼。Blender FBX 导出器自动在 armature 根节点添加 scale=100(m→cm)，**不需要 Send2UE 的猴补丁**。
2. **朝向**: Y-forward/Z-up 导出 → UE 里 Y→-Y 翻转，正确右手系→左手系转换，无镜像。
3. **尺寸验证**: 2m Cube → UE 精确 200x200x200 cm。
4. **UE API**: `FbxAnimSequenceImportData` 可设属性有限，无 `animation_length` / `import_bone_tracks`。

---

## 四、文件清单

### addon 源码(已推送到 GitHub)

| 文件 | 行数 | 说明 |
|------|------|------|
| `addon/blender_ue_bridge.py` | 713 | addon 主体 v0.3.0，含 UI 面板 + FBX 导出 + UE 导入 |
| `addon/bridge_api.py` | 495 | MCP API 层，供 AI 通过 execute_py 调用 |

### Blender 运行时位置

```
%APPDATA%\Blender Foundation\Blender\5.1\scripts\addons\
├── blender_ue_bridge.py  (addon 主体)
└── bridge_api.py         (MCP API)
```

---

## 五、使用方式

### 方式 A: Blender UI 面板

1. 打开 Blender → Edit → Preferences → Add-ons → 启用 "Blender UE Bridge"
2. N 面板 → UE Bridge 标签
3. 点 "Connect To UE" → 选中物体 → 点 "Send Selected To UE"

### 方式 B: MCP / AI 驱动

在 Qoder 中通过 Blender MCP execute_py 调用:

```python
import bridge_api

# 查看状态
bridge_api.status()

# 连接 UE
bridge_api.connect()

# 一键发送选中物体
bridge_api.send_selected()

# 自定义参数
bridge_api.send_selected(target_path="/Game/Characters", spawn=True)
```

---

## 六、环境依赖

| 组件 | 版本 | 路径 |
|------|------|------|
| Blender | 5.1.0 | `D:\blender\blender.exe` |
| UE | 5.8.3 | `D:\ue\UE_5.8\` |
| UE 测试项目 | - | `D:\test\` |
| remote_execution.py | UE 自带 | `D:\ue\UE_5.8\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python\` |

### UE 端配置

`D:\test\Config\DefaultEngine.ini` 已启用:
```ini
[/Script/PythonScriptPlugin.PythonScriptPluginSettings]
bRemoteExecution=True
RemoteExecutionMulticastGroupEndpoint=239.0.0.1:6766
RemoteExecutionMulticastBindAddress=127.0.0.1
```

---

## 七、已知问题

1. **动画 FPS 微偏**: Act_wave 20帧导出为 0.633s → 31.58 FPS(目标 30)，可接受范围。
2. **UE 连接残留**: 长时间不操作后 TCP 命令端口可能进入 CLOSE_WAIT，需在 UE Python 控制台执行 `unreal.PythonScriptPlugin.reload_scripts()` 或禁用/启用 Python Script Plugin。
3. **replace_existing 首次导入**: 第一次导入某资产时如果之前有残留，动画资产可能不生成，改名重新导入可解决。

---

## 八、后续扩展方向

- 批量导出(多物体分别导出到不同 UE 路径)
- 材质/贴图传输
- LOD 自动生成
- 碰撞体 UCX_ 前缀自动识别
- 复杂角色压力测试(待执行)

---

## 九、下一步:复杂角色压力测试

用户计划在新窗口中使用复杂角色模型进行压力测试，验证:
- 多骨骼 + 多蒙皮网格的导出稳定性
- 多个 Action 同时导出的 AnimSequence 生成
- 大文件 FBX 导出耗时
- UE 导入后骨骼/动画完整性
