# -*- coding: utf-8 -*-
bl_info = {
    "name": "Blender UE Bridge",
    "author": "SAHANA304",
    "version": (0, 3, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > UE Bridge",
    "description": "One-click send selected static/skeletal meshes and animations from Blender to Unreal Engine 5. Verified on Blender 5.1 / UE 5.8.",
    "category": "Pipeline",
}

import base64
import json
import os
import re
import sys
import tempfile
import time

import bpy


# FBX export parameters empirically verified on Blender 5.1 -> UE 5.8 (Phase 0b):
# a 2m cube imports as exactly 200cm. global_scale must stay 1.0 (NOT 100).
FBX_EXPORT_PARAMS = dict(
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

# Skeletal mesh FBX export parameters (Phase 2a verified, Phase 3 updated for animation):
# global_scale=1.0 works for skeletal too — FBX exporter auto-adds scale=100
# on armature root node for m→cm conversion. No monkey patch needed.
# Animation parameters (Phase 3 verified): bake_anim=True exports all actions on the armature.
FBX_SKELETAL_EXPORT_PARAMS = dict(
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

DEFAULT_UE_PYTHON_DIR = "D:/ue/UE_5.8/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python"

RESULT_MARKER = "BRIDGE_RESULT_JSON"


# --------------------------------------------------------------------- utils
def safe_file_name(name):
    """Lowercase filesystem-safe name (plugin-ux-principles naming rule)."""
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9_-]', '_', name)
    return name or 'unnamed'


def sanitize_asset_name(name):
    """Case-preserving name safe for a UE asset (alnum + underscore)."""
    name = re.sub(r'[^A-Za-z0-9_]', '_', name.strip())
    return name or 'unnamed'


def staging_dir_path():
    """Resolve the staging dir without creating it (safe to call in draw())."""
    blend_path = bpy.data.filepath
    if blend_path:
        root = os.path.dirname(blend_path)
    else:
        root = os.path.join(tempfile.gettempdir(), "blender_ue_bridge")
    return os.path.join(root, "_stage", "ue_bridge")


# ------------------------------------------------------------- connection mgr
_RX_MOD = None
_RX = None
_NODE_ID = None
_NODE_INFO = ""


def _get_prefs(context):
    addon = context.preferences.addons.get(__name__)
    return addon.preferences if addon else None


def _load_rx(context):
    global _RX_MOD
    if _RX_MOD is not None:
        return _RX_MOD
    prefs = _get_prefs(context)
    if prefs is None:
        raise RuntimeError("addon preferences not available")
    ue_dir = bpy.path.abspath(prefs.ue_python_dir)
    rx_path = os.path.join(ue_dir, "remote_execution.py")
    if not os.path.exists(rx_path):
        raise RuntimeError("remote_execution.py not found: %s" % rx_path)
    if ue_dir not in sys.path:
        sys.path.insert(0, ue_dir)
    import remote_execution as rx
    _RX_MOD = rx
    return rx


def disconnect():
    global _RX, _NODE_ID, _NODE_INFO
    if _RX is not None:
        try:
            _RX.stop()
        except Exception:
            pass
    _RX = None
    _NODE_ID = None
    _NODE_INFO = ""


def is_connected():
    return _RX is not None and _NODE_ID is not None


def connect(context):
    """Discover a running UE editor via multicast and open a command channel.

    Returns (ok, info_string).
    """
    global _RX, _NODE_ID, _NODE_INFO
    rx = _load_rx(context)
    prefs = _get_prefs(context)
    timeout = prefs.connect_timeout if prefs else 6.0

    disconnect()

    _RX = rx.RemoteExecution(rx.RemoteExecutionConfig())
    _RX.start()

    node = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        nodes = _RX.remote_nodes
        if nodes:
            node = nodes[0]
            break
        time.sleep(0.25)

    if not node or not node.get('node_id'):
        disconnect()
        return False, "no UE editor discovered (is UE running with Remote Execution enabled?)"

    _NODE_ID = node['node_id']
    _RX.open_command_connection(_NODE_ID)
    _NODE_INFO = "%s | %s" % (node.get('project_name', '?'), node.get('engine_version', '?'))
    return True, _NODE_INFO


def run_ue_command(context, command, retry=True):
    """Run a Python command inside UE. Auto-reconnects once on failure."""
    if not is_connected():
        ok, info = connect(context)
        if not ok:
            raise RuntimeError(info)
    try:
        return _RX.run_command(command, exec_mode=_RX_MOD.MODE_EXEC_FILE, raise_on_failure=False)
    except Exception:
        if not retry:
            raise
        ok, info = connect(context)
        if not ok:
            raise RuntimeError(info)
        return _RX.run_command(command, exec_mode=_RX_MOD.MODE_EXEC_FILE, raise_on_failure=False)


# ------------------------------------------------------------- FBX + UE glue
def export_mesh_fbx(mesh_obj, staging_dir):
    """Select only mesh_obj, export it to FBX with the locked params. Returns path."""
    os.makedirs(staging_dir, exist_ok=True)
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except Exception:
            pass
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj

    fbx_path = os.path.join(staging_dir, safe_file_name(mesh_obj.name) + ".fbx")
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win):
        bpy.ops.export_scene.fbx(filepath=fbx_path, **FBX_EXPORT_PARAMS)
    return fbx_path


def export_skeletal_fbx(armature_obj, staging_dir):
    """Select armature + its skinned meshes, export as skeletal FBX. Returns path."""
    os.makedirs(staging_dir, exist_ok=True)

    # Find all meshes skinned to this armature
    skinned_meshes = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.modifiers.get('Armature'):
            if obj.modifiers['Armature'].object == armature_obj:
                skinned_meshes.append(obj)

    if not skinned_meshes:
        raise RuntimeError("No meshes skinned to armature '%s'" % armature_obj.name)

    # Deselect all, then select armature + skinned meshes
    for o in bpy.data.objects:
        try:
            o.select_set(False)
        except Exception:
            pass
    armature_obj.select_set(True)
    for m in skinned_meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    fbx_path = os.path.join(staging_dir, safe_file_name(armature_obj.name) + "_skeletal.fbx")
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win):
        bpy.ops.export_scene.fbx(filepath=fbx_path, **FBX_SKELETAL_EXPORT_PARAMS)
    return fbx_path


# UE-side import script. Payload is passed as base64 JSON to avoid any escaping
# issues across the XML/HTTP command channel. Pure ASCII.
_UE_IMPORT_SCRIPT = r'''
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
'''.replace("__MARKER__", RESULT_MARKER)


# UE-side skeletal mesh import script (Phase 3: supports animation import).
_UE_SKELETAL_IMPORT_SCRIPT = r'''
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
    # Collect animation sequences
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
'''.replace("__MARKER__", RESULT_MARKER)


def build_ue_command(assets, target_path, spawn, use_sm_prefix):
    payload = {
        "target_path": target_path,
        "spawn": spawn,
        "use_sm_prefix": use_sm_prefix,
        "assets": assets,
    }
    b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return _UE_IMPORT_SCRIPT.replace("__PAYLOAD_B64__", b64)


def build_ue_skeletal_command(assets, target_path, spawn):
    payload = {
        "target_path": target_path,
        "spawn": spawn,
        "assets": assets,
    }
    b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return _UE_SKELETAL_IMPORT_SCRIPT.replace("__PAYLOAD_B64__", b64)


def parse_bridge_result(res):
    for line in res.get('output', []):
        txt = line.get('output', '')
        if RESULT_MARKER in txt:
            js = txt.split(RESULT_MARKER, 1)[1].strip()
            try:
                return json.loads(js)
            except Exception:
                return None
    return None


# --------------------------------------------------------------- preferences
class BRIDGE_preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    ue_python_dir: bpy.props.StringProperty(
        name="UE Python Dir",
        description="Folder containing UE's remote_execution.py (PythonScriptPlugin/Content/Python)",
        default=DEFAULT_UE_PYTHON_DIR,
        subtype='DIR_PATH',
    )
    connect_timeout: bpy.props.FloatProperty(
        name="Connect Timeout (s)",
        default=6.0, min=1.0, max=30.0,
        description="Seconds to wait for UE multicast discovery",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "ue_python_dir")
        layout.prop(self, "connect_timeout")
        try:
            rx = os.path.join(bpy.path.abspath(self.ue_python_dir), "remote_execution.py")
            ok = os.path.exists(rx)
        except Exception:
            ok = False
        layout.label(
            text=("remote_execution.py found" if ok else "remote_execution.py NOT found"),
            icon=('INFO' if ok else 'ERROR'),
        )


# ------------------------------------------------------------ scene settings
class BRIDGE_scene_props(bpy.types.PropertyGroup):
    ue_target_path: bpy.props.StringProperty(
        name="UE Target Path",
        default="/Game/BridgeImport",
        description="Content Browser folder to import into",
    )
    spawn_to_level: bpy.props.BoolProperty(
        name="Spawn To Level",
        default=True,
        description="Spawn the imported mesh as an actor in the current level",
    )
    use_sm_prefix: bpy.props.BoolProperty(
        name="SM_ Prefix",
        default=True,
        description="Prefix imported static mesh assets with SM_ (UE naming convention)",
    )
    last_result: bpy.props.StringProperty(name="Last Result", default="")


# ----------------------------------------------------------------- operators
class BRIDGE_OT_connect(bpy.types.Operator):
    bl_idname = "ue_bridge.connect"
    bl_label = "Connect To UE"
    bl_description = "Discover a running Unreal Editor and open a command connection"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.bridge
        try:
            ok, info = connect(context)
        except Exception as e:
            props.last_result = "connect error: %s" % str(e)[:120]
            self.report({'ERROR'}, props.last_result)
            return {'CANCELLED'}
        if ok:
            props.last_result = "connected: %s" % info
            self.report({'INFO'}, "UE connected: %s" % info)
            return {'FINISHED'}
        props.last_result = info
        self.report({'WARNING'}, info)
        return {'CANCELLED'}


class BRIDGE_OT_send_selected(bpy.types.Operator):
    bl_idname = "ue_bridge.send_selected"
    bl_label = "Send Selected To UE"
    bl_description = "Export selected meshes/armatures to FBX, then import and spawn them in Unreal"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.bridge

        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        armatures = [o for o in context.selected_objects if o.type == 'ARMATURE']

        if not meshes and not armatures:
            props.last_result = "no mesh or armature objects selected"
            self.report({'WARNING'}, props.last_result)
            return {'CANCELLED'}

        staging = staging_dir_path()
        static_assets = []
        skeletal_assets = []

        # 1a. Export static meshes (meshes NOT skinned to selected armatures)
        skinned_mesh_names = set()
        for arm in armatures:
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.modifiers.get('Armature'):
                    if obj.modifiers['Armature'].object == arm:
                        skinned_mesh_names.add(obj.name)

        static_meshes = [m for m in meshes if m.name not in skinned_mesh_names]
        try:
            for m in static_meshes:
                fbx = export_mesh_fbx(m, staging)
                static_assets.append({
                    "fbx": fbx.replace("\\", "/"),
                    "name": sanitize_asset_name(m.name),
                })
        except Exception as e:
            props.last_result = "static export error: %s" % str(e)[:120]
            self.report({'ERROR'}, props.last_result)
            return {'CANCELLED'}

        # 1b. Export skeletal meshes (armature + skinned meshes)
        try:
            for arm in armatures:
                fbx = export_skeletal_fbx(arm, staging)
                skeletal_assets.append({
                    "fbx": fbx.replace("\\", "/"),
                    "name": sanitize_asset_name(arm.name),
                })
        except Exception as e:
            props.last_result = "skeletal export error: %s" % str(e)[:120]
            self.report({'ERROR'}, props.last_result)
            return {'CANCELLED'}

        # 2. Import static meshes in UE
        static_results = []
        if static_assets:
            cmd = build_ue_command(static_assets, props.ue_target_path, props.spawn_to_level, props.use_sm_prefix)
            try:
                res = run_ue_command(context, cmd)
            except Exception as e:
                props.last_result = "ue static error: %s" % str(e)[:120]
                self.report({'ERROR'}, props.last_result)
                return {'CANCELLED'}

            if not res.get('success', False):
                detail = ""
                for line in res.get('output', []):
                    if line.get('type') == 'Error':
                        detail += line.get('output', '')
                props.last_result = "ue static failed: %s" % (detail[:120] or "unknown")
                self.report({'ERROR'}, props.last_result)
                return {'CANCELLED'}

            static_results = parse_bridge_result(res) or []

        # 3. Import skeletal meshes in UE
        skeletal_results = []
        if skeletal_assets:
            cmd = build_ue_skeletal_command(skeletal_assets, props.ue_target_path, props.spawn_to_level)
            try:
                res = run_ue_command(context, cmd)
            except Exception as e:
                props.last_result = "ue skeletal error: %s" % str(e)[:120]
                self.report({'ERROR'}, props.last_result)
                return {'CANCELLED'}

            if not res.get('success', False):
                detail = ""
                for line in res.get('output', []):
                    if line.get('type') == 'Error':
                        detail += line.get('output', '')
                props.last_result = "ue skeletal failed: %s" % (detail[:120] or "unknown")
                self.report({'ERROR'}, props.last_result)
                return {'CANCELLED'}

            skeletal_results = parse_bridge_result(res) or []

        # 4. Combine results
        all_results = static_results + skeletal_results
        if not all_results:
            props.last_result = "done (no result payload parsed)"
            self.report({'INFO'}, props.last_result)
            return {'FINISHED'}

        summary = []
        for r in all_results:
            if r.get('error'):
                summary.append("%s: ERROR %s" % (r.get('name'), r['error'][:40]))
            elif not r.get('loaded'):
                summary.append("%s: import produced no asset" % r.get('name'))
            else:
                asset_type = r.get('type', 'static')
                if asset_type == 'skeletal':
                    bbox_min = r.get('bbox_min_cm')
                    bbox_max = r.get('bbox_max_cm')
                    bbox_txt = (" bbox=%s..%s" % (bbox_min, bbox_max)) if bbox_min else ""
                    sp_txt = (" spawned" if r.get('spawned') else "")
                    summary.append("%s: skeletal ok%s%s" % (r.get('name'), bbox_txt, sp_txt))
                else:
                    sz = r.get('size_cm')
                    sz_txt = (" size_cm=%s" % sz) if sz else ""
                    sp_txt = (" spawned" if r.get('spawned') else "")
                    summary.append("%s: static ok%s%s" % (r.get('name'), sz_txt, sp_txt))
        props.last_result = "\n".join(summary)
        self.report({'INFO'}, "Sent %d asset(s) to UE (%d static, %d skeletal)" % (
            len(all_results), len(static_results), len(skeletal_results)))
        return {'FINISHED'}


# --------------------------------------------------------------------- panel
class BRIDGE_PT_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'UE Bridge'
    bl_label = 'Blender UE Bridge'

    def draw(self, context):
        layout = self.layout

        # connection status (block 1)
        box = layout.box()
        try:
            if is_connected():
                box.label(text="UE: connected", icon='INFO')
                if _NODE_INFO:
                    box.label(text=_NODE_INFO)
            else:
                box.label(text="UE: not connected", icon='ERROR')
        except Exception:
            box.label(text="status unavailable", icon='ERROR')
        try:
            box.operator("ue_bridge.connect", icon='FILE_REFRESH',
                         text=("Reconnect" if is_connected() else "Connect To UE"))
        except Exception:
            pass

        # settings (block 2)
        try:
            props = context.scene.bridge
            layout.prop(props, "ue_target_path")
            layout.prop(props, "spawn_to_level")
            layout.prop(props, "use_sm_prefix")
        except Exception as e:
            layout.label(text="settings error", icon='ERROR')

        # selection (block 3)
        try:
            meshes = [o for o in context.selected_objects if o.type == 'MESH']
            armatures = [o for o in context.selected_objects if o.type == 'ARMATURE']
            layout.label(text="Selected meshes: %d" % len(meshes), icon='MESH_DATA')
            layout.label(text="Selected armatures: %d" % len(armatures), icon='ARMATURE_DATA')
        except Exception:
            layout.label(text="Selected: ?", icon='MESH_DATA')

        # staging dir (block 4)
        try:
            row = layout.row()
            row.label(text="Staging:", icon='FILE_FOLDER')
            layout.label(text=staging_dir_path())
        except Exception:
            layout.label(text="staging unavailable", icon='ERROR')

        # action (block 5)
        try:
            layout.operator("ue_bridge.send_selected", icon='EXPORT')
        except Exception:
            pass

        # last result (block 6)
        try:
            props = context.scene.bridge
            if props.last_result:
                rbox = layout.box()
                rbox.label(text="Last result:", icon='INFO')
                for ln in str(props.last_result).split("\n")[:10]:
                    rbox.label(text=ln[:60])
        except Exception:
            pass


# ------------------------------------------------------------------ register
classes = (
    BRIDGE_preferences,
    BRIDGE_scene_props,
    BRIDGE_OT_connect,
    BRIDGE_OT_send_selected,
    BRIDGE_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bridge = bpy.props.PointerProperty(type=BRIDGE_scene_props)


def unregister():
    disconnect()
    try:
        del bpy.types.Scene.bridge
    except Exception:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()
