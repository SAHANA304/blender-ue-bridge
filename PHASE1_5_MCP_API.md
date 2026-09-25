# Phase 1.5: MCP 封装

> AI 通过 Blender MCP execute_py 驱动 Blender→UE 桥接管线。

## 架构

```
AI (Qoder)
  │
  ├── mcp__blender__execute_py  →  import bridge_api; bridge_api.send_selected()
  │                                      │
  │                                      ├── FBX export (Blender Python)
  │                                      ├── UE Remote Execution (TCP command)
  │                                      └── JSON result → AI 可读
  │
  └── mcp__blender__get_scene_info  →  查看当前场景
```

## bridge_api.py 函数清单

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `connect(timeout=6.0)` | timeout: float | `{"ok": bool, "info": str}` | 发现并连接 UE 编辑器 |
| `disconnect()` | 无 | `{"ok": True}` | 断开 UE 连接 |
| `status()` | 无 | JSON object | 连接状态 + 场景物体列表 |
| `send_selected(target_path, spawn, use_sm_prefix)` | 三个可选参数 | JSON object | 导出选中物体→UE 导入+spawn |

### send_selected 返回格式

```json
{
  "ok": true,
  "total": 2,
  "static": 1,
  "skeletal": 1,
  "results": [
    {"name": "SM_Cube", "asset": "/Game/BridgeImport/SM_Cube", "loaded": true, "size_cm": [200, 200, 200], "spawned": true},
    {"name": "SK_TestRig", "asset": "/Game/BridgeImport/SK_TestRig", "loaded": true, "type": "skeletal", "bbox_min_cm": [...], "bbox_max_cm": [...], "spawned": true, "animations": [{"path": "...", "length": 0.6667}]}
  ]
}
```

## AI 调用示例

### 1. 查看场景

```python
# execute_py
import bridge_api
bridge_api.status()
```

### 2. 连接 UE

```python
import bridge_api
bridge_api.connect()
```

### 3. 一键发送

```python
import bridge_api
bridge_api.send_selected()
```

### 4. 自定义目标路径

```python
import bridge_api
bridge_api.send_selected(target_path="/Game/Characters", spawn=True)
```

### 5. 只导出不 spawn

```python
import bridge_api
bridge_api.send_selected(spawn=False)
```

## 典型 AI 工作流

1. `get_scene_info()` → 了解场景内容
2. 用户说"把选中的模型发到 UE"
3. `execute_py: import bridge_api; bridge_api.send_selected()`
4. 读取返回 JSON → 告知用户结果

## 文件位置

- 源文件: `addon/bridge_api.py`
- Blender addons: `%APPDATA%/Blender Foundation/Blender/5.1/scripts/addons/bridge_api.py`
- 与 `blender_ue_bridge.py` (addon v0.3.0) 并行存在，共享 FBX 参数和 UE 脚本模板

## 依赖

- Blender 5.1 + Qoder Bridge addon（MCP 连接）
- UE 5.8 + Remote Execution 启用
- `remote_execution.py` 路径: `D:/ue/UE_5.8/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python/`

## 状态

- **bridge_api.py 已创建**，语法验证通过
- **待测试**: 需要 Blender MCP 连接（Qoder Bridge addon 启用）
