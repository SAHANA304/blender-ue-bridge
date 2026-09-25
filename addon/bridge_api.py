# -*- coding: utf-8 -*-
"""
Blender UE Bridge -- MCP API layer.

Called by AI through Blender MCP execute_py.
Every public function returns a plain dict (JSON-serialisable).

Usage from execute_py:
    import bridge_api
    bridge_api.connect()
    bridge_api.send_selected()
"""

import json
import os
import re
import sys
import tempfile
import time

import bpy

DEFAULT_UE_PYTHON_DIR = (
    "D:/ue/UE_5.8/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python"
)

# ---- internal state ---------------------------------------------------------

_rx_mod = None
_rx = None
_node_id = None
_node_info = ""


def _ensure_ue_python_on_path():
    ue_dir = DEFAULT_UE_PYTHON_DIR
    if not os.path.isdir(ue_dir):
        raise RuntimeError("UE Python dir not found: %s" % ue_dir)
    rx_path = os.path.join(ue_dir, "remote_execution.py")
    if not os.path.exists(rx_path):
        raise RuntimeError("remote_execution.py not found: %s" % rx_path)
    if ue_dir not in sys.path:
        sys.path.insert(0, ue_dir)


def _get_rx_mod():
    global _rx_mod
    if _rx_mod is not None:
        return _rx_mod
    _ensure_ue_python_on_path()
    import remote_execution as rx
    _rx_mod = rx
    return rx


def _safe_file_name(name):
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9_-]', '_', name)
    return name or 'unnamed'


def _sanitize_asset_name(name):
    name = re.sub(r'[^A-Za-z0-9_]', '_', name.strip())
    return name or 'unnamed'


def _staging_dir():
    blend_path = bpy.data.filepath
    if blend_path:
        root = os.path.dirname(blend_path)
    else:
        root = os.path.join(tempfile.gettempdir(), "blender_ue_bridge")
    return os.path.join(root, "_stage", "ue_bridge")


# ---- FBX export params (locked, verified Phase 0b-3) -----------------------

_FBX_STATIC = dict(
    use_selection=True,
    global_scale=1.0,
    apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_NONE',
    axis_forward='Y',
    axis_up='Z',
    object_types={'MESH'},
    use_mesh_modifiers=True,
    bake_space_transform=False,
    mesh_smooth_type='OFF',
)

_FBX_SKELETAL = dict(
    use_selection=True,
    global_scale=1.0,
    apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_NONE',
    axis_forward='Y',
    axis_up='Z',
    object_types={'ARMATURE', 'MESH'},
    use_mesh_modifiers=True,
    bake_space_transform=False,
    mesh_smooth_type='OFF',
    primary_bone_axis='Y',
    secondary_bone_axis='X',
    armature_nodetype='NULL',
    add_leaf_bones=False,
    use_armature_deform_only=True,
    bake_anim=True,
    bake_anim_use_all_bones=True,
    bake_anim_force_startend_keying=True,
    bake_anim_step=1.0,
    bake_anim_simplify_factor=0.0,
)

# ---- UE-side import scripts ------------------------------------------------

_RESULT_MARKER = "BRIDGE_RESULT_JSON"

_UE_STATIC_SCRIPT = r'''
import unreal, json, base64
payload = json.loads(base64.b64decode("__PAYLOAD_B64__").decode("utf-8"))
target = payload["target_path"]
do_spawn = payload["spawn"]
use_sm = payload["use_sm_prefix"]
at = unreal.AssetToolsHelpers.get_asset_tools()
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
results = []
spacing = 300.0
i = 0
for a in payload["assets"]:
    name = a["name"]
    if use_sm and not name.startswith("SM_"):
        name = "SM_" + name
    task = unreal.AssetImportTask()
    task.filename = a["fbx"]
    task.destination_path = target
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    o = unreal.FbxImportUI()
    o.import_mesh = True
    o.import_as_skeletal = False
    o.import_animations = False
    o.import_materials = False
    o.import_textures = False
    task.options = o
    try:
        at.import_asset_tasks([task])
    except Exception as e:
        results.append({"name": name, "error": str(e)})
        i += 1
        continue
    paths = [str(p) for p in task.imported_object_paths]
    asset_path = paths[0] if paths else (target + "/" + name)
    sm = unreal.EditorAssetLibrary.load_asset(asset_path)
    line = {"name": name, "asset": asset_path, "loaded": sm is not None}
    if sm is not None:
        try:
            bb = sm.get_bounding_box()
            line["size_cm"] = [round(bb.max.x - bb.min.x, 2), round(bb.max.y - bb.min.y, 2), round(bb.max.z - bb.min.z, 2)]
        except Exception as e:
            line["bbox_error"] = str(e)
        if do_spawn:
            try:
                actor = eas.spawn_actor_from_object(sm, unreal.Vector(i * spacing, 0.0, 100.0))
                line["spawned"] = actor is not None
            except Exception as e:
                line["spawn_error"] = str(e)
    results.append(line)
    i += 1
print("__MARKER__" + json.dumps(results))
'''.replace("__MARKER__", _RESULT_MARKER)

_UE_SKELETAL_SCRIPT = r'''
import unreal, json, base64
payload = json.loads(base64.b64decode("__PAYLOAD_B64__").decode("utf-8"))
target = payload["target_path"]
do_spawn = payload["spawn"]
at = unreal.AssetToolsHelpers.get_asset_tools()
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
results = []
spacing = 300.0
i = 0
for a in payload["assets"]:
    name = a["name"]
    if not name.startswith("SK_"):
        name = "SK_" + name
    task = unreal.AssetImportTask()
    task.filename = a["fbx"]
    task.destination_path = target
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    o = unreal.FbxImportUI()
    o.import_mesh = True
    o.import_as_skeletal = True
    o.import_animations = True
    o.import_materials = False
    o.import_textures = False
    task.options = o
    try:
        at.import_asset_tasks([task])
    except Exception as e:
        results.append({"name": name, "error": str(e)})
        i += 1
        continue
    paths = [str(p) for p in task.imported_object_paths]
    asset_path = paths[0] if paths else (target + "/" + name)
    skm = unreal.EditorAssetLibrary.load_asset(asset_path)
    line = {"name": name, "asset": asset_path, "loaded": skm is not None, "type": "skeletal"}
    if skm is not None:
        try:
            bounds = skm.get_bounds()
            origin = bounds.origin
            extent = bounds.box_extent
            line["bbox_min_cm"] = [round(origin.x - extent.x, 2), round(origin.y - extent.y, 2), round(origin.z - extent.z, 2)]
            line["bbox_max_cm"] = [round(origin.x + extent.x, 2), round(origin.y + extent.y, 2), round(origin.z + extent.z, 2)]
        except Exception as e:
            line["bbox_error"] = str(e)
        if do_spawn:
            try:
                actor = eas.spawn_actor_from_object(skm, unreal.Vector(i * spacing, 0.0, 100.0))
                line["spawned"] = actor is not None
            except Exception as e:
                line["spawn_error"] = str(e)
    anim_sequences = []
    for p in paths:
        asset = unreal.EditorAssetLibrary.load_asset(p)
        if asset and asset.get_class().get_name() == "AnimSequence":
            try:
                seq_len = asset.get_editor_property("sequence_length")
                anim_sequences.append({"path": p, "length": round(seq_len, 4)})
            except:
                anim_sequences.append({"path": p})
    if anim_sequences:
        line["animations"] = anim_sequences
    results.append(line)
    i += 1
print("__MARKER__" + json.dumps(results))
'''.replace("__MARKER__", _RESULT_MARKER)


# ---- connection -------------------------------------------------------------

def connect(timeout=6.0):
    """Discover UE editor and open command channel. Returns JSON status."""
    global _rx, _node_id, _node_info
    try:
        rx = _get_rx_mod()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    disconnect()

    _rx = rx.RemoteExecution(rx.RemoteExecutionConfig())
    _rx.start()

    node = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        nodes = _rx.remote_nodes
        if nodes:
            node = nodes[0]
            break
        time.sleep(0.25)

    if not node or not node.get('node_id'):
        disconnect()
        return {"ok": False, "error": "no UE editor discovered"}

    _node_id = node['node_id']
    _rx.open_command_connection(_node_id)
    _node_info = "%s | %s" % (
        node.get('project_name', '?'),
        node.get('engine_version', '?'),
    )
    return {"ok": True, "info": _node_info}


def disconnect():
    """Close UE connection."""
    global _rx, _node_id, _node_info
    if _rx is not None:
        try:
            _rx.stop()
        except Exception:
            pass
    _rx = None
    _node_id = None
    _node_info = ""
    return {"ok": True}


def status():
    """Return connection status and scene summary."""
    objects = []
    for obj in bpy.data.objects:
        objects.append({
            "name": obj.name,
            "type": obj.type,
            "selected": obj.select_get(),
            "location": list(obj.location),
        })
    return {
        "connected": _rx is not None and _node_id is not None,
        "ue_info": _node_info,
        "blend_file": bpy.data.filepath or "(unsaved)",
        "object_count": len(bpy.data.objects),
        "objects": objects,
    }


# ---- send to UE ------------------------------------------------------------

def send_selected(target_path="/Game/BridgeImport", spawn=True, use_sm_prefix=True):
    """Export selected objects to FBX, import + spawn in UE.

    Returns JSON with per-asset results.
    """
    if not (_rx is not None and _node_id is not None):
        result = connect()
        if not result.get("ok"):
            return {"ok": False, "error": "connect failed: " + result.get("error", "?")}

    sel = bpy.context.selected_objects
    meshes = [o for o in sel if o.type == 'MESH']
    armatures = [o for o in sel if o.type == 'ARMATURE']

    if not meshes and not armatures:
        return {"ok": False, "error": "no mesh or armature selected"}

    staging = _staging_dir()
    os.makedirs(staging, exist_ok=True)

    skinned_names = set()
    for arm in armatures:
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.modifiers.get('Armature'):
                if obj.modifiers['Armature'].object == arm:
                    skinned_names.add(obj.name)

    static_meshes = [m for m in meshes if m.name not in skinned_names]
    static_assets = []
    for m in static_meshes:
        try:
            fbx = _export_static(m, staging)
            static_assets.append({
                "fbx": fbx.replace("\\", "/"),
                "name": _sanitize_asset_name(m.name),
            })
        except Exception as e:
            return {"ok": False, "error": "export static '%s': %s" % (m.name, e)}

    skeletal_assets = []
    for arm in armatures:
        try:
            fbx = _export_skeletal(arm, staging)
            skeletal_assets.append({
                "fbx": fbx.replace("\\", "/"),
                "name": _sanitize_asset_name(arm.name),
            })
        except Exception as e:
            return {"ok": False, "error": "export skeletal '%s': %s" % (arm.name, e)}

    all_results = []

    if static_assets:
        res = _ue_import_static(static_assets, target_path, spawn, use_sm_prefix)
        if not res.get("ok"):
            return res
        all_results.extend(res.get("results", []))

    if skeletal_assets:
        res = _ue_import_skeletal(skeletal_assets, target_path, spawn)
        if not res.get("ok"):
            return res
        all_results.extend(res.get("results", []))

    return {
        "ok": True,
        "total": len(all_results),
        "static": len(static_assets),
        "skeletal": len(skeletal_assets),
        "results": all_results,
    }


# ---- internal: FBX export --------------------------------------------------

def _export_static(mesh_obj, staging):
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except Exception:
            pass
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj

    fbx_path = os.path.join(staging, _safe_file_name(mesh_obj.name) + ".fbx")
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win):
        bpy.ops.export_scene.fbx(filepath=fbx_path, **_FBX_STATIC)
    return fbx_path


def _export_skeletal(armature_obj, staging):
    skinned = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.modifiers.get('Armature'):
            if obj.modifiers['Armature'].object == armature_obj:
                skinned.append(obj)
    if not skinned:
        raise RuntimeError("no meshes skinned to '%s'" % armature_obj.name)

    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except Exception:
            pass
    armature_obj.select_set(True)
    for m in skinned:
        m.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    fbx_path = os.path.join(staging, _safe_file_name(armature_obj.name) + "_skeletal.fbx")
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win):
        bpy.ops.export_scene.fbx(filepath=fbx_path, **_FBX_SKELETAL)
    return fbx_path


# ---- internal: UE import via remote command --------------------------------

def _build_ue_cmd(script_template, assets, target_path, spawn, extra=None):
    import base64
    payload = {
        "target_path": target_path,
        "spawn": spawn,
        "assets": assets,
    }
    if extra:
        payload.update(extra)
    b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return script_template.replace("__PAYLOAD_B64__", b64)


def _run_ue(command):
    rx = _get_rx_mod()
    return _rx.run_command(command, exec_mode=rx.MODE_EXEC_FILE, raise_on_failure=False)


def _parse_result(res):
    for line in res.get('output', []):
        txt = line.get('output', '')
        if _RESULT_MARKER in txt:
            js = txt.split(_RESULT_MARKER, 1)[1].strip()
            try:
                return json.loads(js)
            except Exception:
                return None
    return None


def _ue_import_static(assets, target_path, spawn, use_sm_prefix):
    cmd = _build_ue_cmd(
        _UE_STATIC_SCRIPT, assets, target_path, spawn,
        extra={"use_sm_prefix": use_sm_prefix},
    )
    try:
        res = _run_ue(cmd)
    except Exception as e:
        return {"ok": False, "error": "ue static: %s" % e}
    if not res.get('success', False):
        detail = ""
        for line in res.get('output', []):
            if line.get('type') == 'Error':
                detail += line.get('output', '')
        return {"ok": False, "error": "ue static failed: %s" % (detail or "unknown")}
    return {"ok": True, "results": _parse_result(res) or []}


def _ue_import_skeletal(assets, target_path, spawn):
    cmd = _build_ue_cmd(_UE_SKELETAL_SCRIPT, assets, target_path, spawn)
    try:
        res = _run_ue(cmd)
    except Exception as e:
        return {"ok": False, "error": "ue skeletal: %s" % e}
    if not res.get('success', False):
        detail = ""
        for line in res.get('output', []):
            if line.get('type') == 'Error':
                detail += line.get('output', '')
        return {"ok": False, "error": "ue skeletal failed: %s" % (detail or "unknown")}
    return {"ok": True, "results": _parse_result(res) or []}
