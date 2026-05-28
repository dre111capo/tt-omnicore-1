# Blender automation script for rendering OmniCore-1 3D Stacked IMC Cube
# Run inside Blender using: blender --background --python blender_render_cube.py

import bpy
import math

def clean_scene():
    """
    Clears all existing objects, cameras, lights, and meshes from the default scene.
    """
    # Switch to object mode if not already
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
        
    # Select all and delete
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Delete unused data blocks
    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    for material in bpy.data.materials:
        bpy.data.materials.remove(material)
    for camera in bpy.data.cameras:
        bpy.data.cameras.remove(camera)
    for light in bpy.data.lights:
        bpy.data.lights.remove(light)

def create_metallic_material(name, color, roughness=0.1, metallic=1.0):
    """
    Creates a photorealistic metallic material (Gold/Copper) for the metal traces and TSVs.
    """
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Metallic'].default_value = metallic
        principled.inputs['Roughness'].default_value = roughness
    return mat

def create_silicon_material():
    """
    Creates a dark, reflective silicon wafer material for the CPU base block.
    """
    mat = bpy.data.materials.new(name="WaferSilicon")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        principled.inputs['Base Color'].default_value = (0.05, 0.06, 0.08, 1.0) # Dark gray-blue
        principled.inputs['Metallic'].default_value = 0.9
        principled.inputs['Roughness'].default_value = 0.05
    return mat

def create_glass_material(name, color):
    """
    Creates a semi-transparent colored glass/resin material for the upper IMC memory layers.
    """
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if principled:
        principled.inputs['Base Color'].default_value = color
        principled.inputs['Roughness'].default_value = 0.1
        # Set transmission (glass/transparency)
        principled.inputs['Transmission Weight'].default_value = 0.85
        principled.inputs['IOR'].default_value = 1.45
    return mat

def build_3d_ic_cube(obj_mesh_path):
    """
    Imports the layout mesh, extrudes the traces, builds the silicon base, TSV interconnections, and memory layers.
    """
    # 1. Silicon WAFER Base (Central CPU Core)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -0.5))
    cpu_core = bpy.context.active_object
    cpu_core.name = "Central_CPU_Core"
    cpu_core.scale = (200.0, 200.0, 5.0) # Flat wide base representation
    cpu_core.data.materials.append(create_silicon_material())

    # 2. Import parsed layout OBJ mesh
    if obj_mesh_path and math.os.path.exists(obj_mesh_path):
        bpy.ops.wm.obj_import(filepath=obj_mesh_path)
        # Apply metallic material to imported objects
        gold_mat = create_metallic_material("ShinyGold", (1.0, 0.84, 0.0, 1.0))
        for obj in bpy.context.selected_objects:
            obj.data.materials.append(gold_mat)
            # Add Solidify modifier to give layout layers depth
            mod = obj.modifiers.new(name="Solidify", type='SOLIDIFY')
            mod.thickness = 0.3
    else:
        print("OBJ mesh layout not found or skipped. Generating mock geometric memory slices...")

    # 3. Transparent IMC Memory layers (Semi-transparent amber/blue stacked cuboids)
    amber_glass = create_glass_material("AmberIMC", (1.0, 0.5, 0.0, 1.0))
    blue_glass = create_glass_material("BlueIMC", (0.0, 0.3, 1.0, 1.0))
    
    for layer_idx in range(4):
        z_pos = 10.0 + (layer_idx * 12.0)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, z_pos))
        imc_slice = bpy.context.active_object
        imc_slice.name = f"IMC_Memory_Layer_{layer_idx}"
        imc_slice.scale = (160.0, 160.0, 4.0)
        # Alternate colors for visual separation
        imc_slice.data.materials.append(amber_glass if layer_idx % 2 == 0 else blue_glass)

    # 4. Vertical Through-Silicon Vias (TSVs) interconnecting the stack
    copper_mat = create_metallic_material("TSVCopper", (0.8, 0.3, 0.1, 1.0), roughness=0.15)
    tsv_positions = [
        (-70, -70), (70, -70), (-70, 70), (70, 70),
        (-35, -35), (35, -35), (-35, 35), (35, 35),
        (0, -50), (0, 50), (-50, 0), (50, 0)
    ]
    for idx, (x, y) in enumerate(tsv_positions):
        bpy.ops.mesh.primitive_cylinder_add(radius=2.0, depth=55.0, location=(x, y, 25.0))
        tsv = bpy.context.active_object
        tsv.name = f"TSV_Interconnect_{idx}"
        tsv.data.materials.append(copper_mat)

def setup_lighting_and_rendering():
    """
    Sets up Cycles engine, Three-Point Lighting system, and render output settings.
    """
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 128 # Balanced sample count for batch performance
    
    # 1. Key Light (Strong, warm)
    key_light_data = bpy.data.lights.new(name="KeyLight", type='SUN')
    key_light_data.energy = 5.0
    key_light_data.color = (1.0, 0.95, 0.9)
    key_light = bpy.data.objects.new("KeyLight", key_light_data)
    scene.collection.objects.link(key_light)
    key_light.location = (150, -150, 200)
    key_light.rotation_euler = (math.radians(35), math.radians(45), 0)

    # 2. Fill Light (Soft, cool)
    fill_light_data = bpy.data.lights.new(name="FillLight", type='SUN')
    fill_light_data.energy = 2.0
    fill_light_data.color = (0.85, 0.9, 1.0)
    fill_light = bpy.data.objects.new("FillLight", fill_light_data)
    scene.collection.objects.link(fill_light)
    fill_light.location = (-150, -150, 150)
    fill_light.rotation_euler = (math.radians(45), math.radians(-35), 0)

    # 3. Rim Light (Backlight, highlights edges)
    rim_light_data = bpy.data.lights.new(name="RimLight", type='POINT')
    rim_light_data.energy = 100000.0
    rim_light_data.color = (1.0, 1.0, 1.0)
    rim_light = bpy.data.objects.new("RimLight", rim_light_data)
    scene.collection.objects.link(rim_light)
    rim_light.location = (0, 200, 100)

def setup_camera_animation():
    """
    Configures a cinematic camera rotating 360 degrees around the 3D IMC Cube.
    """
    # Create target empty object at coordinates center
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 20.0))
    target = bpy.context.active_object
    target.name = "CameraTarget"

    # Create camera
    cam_data = bpy.data.cameras.new("CinematicCamera")
    cam = bpy.data.objects.new("CinematicCamera", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (300, -300, 180)

    # Track-To constraint (points camera at target empty)
    constraint = cam.constraints.new(type='TRACK_TO')
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    
    # Active camera selection
    bpy.context.scene.camera = cam

    # Set up rotation path animation for camera
    # Rotate target empty axial to orbit the camera
    target.rotation_mode = 'XYZ'
    target.keyframe_insert(data_path="rotation_euler", frame=1)
    
    target.rotation_euler[2] = math.radians(360)
    target.keyframe_insert(data_path="rotation_euler", frame=120) # 120 frame sequence

    # Force linear interpolation on keyframes
    for fcurve in target.animation_data.action.fcurves:
        for kp in fcurve.keypoints:
            kp.interpolation = 'LINEAR'

if __name__ == "__main__":
    clean_scene()
    build_3d_ic_cube("test/omnicore_3d_mesh.obj")
    setup_lighting_and_rendering()
    setup_camera_animation()
    print("Blender 3D scene generated successfully. Ready for Cycles hardware rendering.")
