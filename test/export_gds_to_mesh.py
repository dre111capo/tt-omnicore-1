#!/usr/bin/env python3
import sys
import os
import struct

# SkyWater 130nm GDS Layer Map for Metals
METAL_LAYERS = {
    67: ("Met1", 0.5),   # Layer 67: Metal 1, Z-height 0.5
    69: ("Met2", 1.5),   # Layer 69: Metal 2, Z-height 1.5
    70: ("Met3", 2.5),   # Layer 70: Metal 3, Z-height 2.5
    72: ("Met4", 3.5),   # Layer 72: Metal 4, Z-height 3.5
}

def parse_gdsii(gds_path):
    """
    Extremely simple GDSII stream parser to extract boundary geometries on metal layers.
    GDSII records: [2 bytes length] [1 byte record type] [1 byte data type] [optional data]
    """
    boundaries = []
    if not os.path.exists(gds_path):
        print(f"Error: GDSII file not found at {gds_path}")
        return boundaries

    with open(gds_path, "rb") as f:
        data = f.read()

    offset = 0
    total_len = len(data)
    
    current_layer = None
    current_xy = []
    in_boundary = False

    while offset < total_len:
        if offset + 4 > total_len:
            break
        
        # Read header
        rec_len, rec_type, data_type = struct.unpack_from(">HBB", data, offset)
        if rec_len < 4:
            break # Corrupted record
            
        rec_data = data[offset+4 : offset+rec_len]
        offset += rec_len
        
        # Record Types:
        # 0x08 = BOUNDARY (Start of boundary)
        # 0x0D = LAYER (Layer specification)
        # 0x10 = XY (Coordinates)
        # 0x11 = ENDEL (End of element)
        
        if rec_type == 0x08:
            in_boundary = True
            current_layer = None
            current_xy = []
        elif rec_type == 0x0D and in_boundary:
            if len(rec_data) >= 2:
                current_layer = struct.unpack(">h", rec_data[:2])[0]
        elif rec_type == 0x10 and in_boundary:
            # Parse coordinates (4-byte signed integers in database units, typically nm or pm)
            num_points = len(rec_data) // 8
            for i in range(num_points):
                x, y = struct.unpack_from(">ii", rec_data, i * 8)
                current_xy.append((x / 1000.0, y / 1000.0)) # Convert to microns
        elif rec_type == 0x11 and in_boundary:
            if current_layer in METAL_LAYERS and len(current_xy) >= 3:
                boundaries.append({
                    "layer": current_layer,
                    "name": METAL_LAYERS[current_layer][0],
                    "z": METAL_LAYERS[current_layer][1],
                    "points": current_xy[:-1] # Remove the closing duplicate point
                })
            in_boundary = False

    return boundaries

def export_to_obj(boundaries, obj_path):
    """
    Exports parsed boundary polygons to a Wavefront OBJ file.
    Different layers are grouped by name with distinct Z coordinates.
    """
    with open(obj_path, "w") as f:
        f.write("# OmniCore-1 3D Stacked Mesh\n")
        f.write("# Generated from GDSII by export_gds_to_mesh.py\n\n")
        
        vertex_count = 1
        for i, b in enumerate(boundaries):
            layer_name = b["name"]
            z = b["z"]
            f.write(f"g {layer_name}_{i}\n")
            
            # Write vertices
            for pt in b["points"]:
                f.write(f"v {pt[0]:.4f} {pt[1]:.4f} {z:.4f}\n")
                
            # Write a simple polygon face
            num_pts = len(b["points"])
            face_indices = " ".join(str(vertex_count + k) for k in range(num_pts))
            f.write(f"f {face_indices}\n\n")
            vertex_count += num_pts
            
    print(f"Exported 3D mesh containing {len(boundaries)} elements to {obj_path}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 export_gds_to_mesh.py <input.gds> <output.obj>")
        # Fallback to generating a dummy layout file for testing if no arguments provided
        gds_in = "gds/tt_um_omnicore.gds"
        obj_out = "test/omnicore_3d_mesh.obj"
    else:
        gds_in = sys.argv[1]
        obj_out = sys.argv[2]

    # Create dummy output directory if needed
    os.makedirs(os.path.dirname(obj_out) or ".", exist_ok=True)
    
    # If GDSII doesn't exist, we generate a synthetic GDSII file or synthetic OBJ for demonstration
    if not os.path.exists(gds_in):
        print(f"GDSII file {gds_in} not found. Generating synthetic OBJ mesh data for Blender script testing...")
        synthetic_boundaries = []
        # Generate some grid lines representing layout routing for Met1 - Met4
        import random
        random.seed(42)
        for layer, (name, z) in METAL_LAYERS.items():
            for _ in range(30): # 30 wire traces per layer
                start_x = random.uniform(-100, 100)
                start_y = random.uniform(-100, 100)
                width = random.uniform(2, 5)
                length = random.uniform(20, 80)
                if random.choice([True, False]): # Horizontal wire
                    pts = [
                        (start_x, start_y),
                        (start_x + length, start_y),
                        (start_x + length, start_y + width),
                        (start_x, start_y + width)
                    ]
                else: # Vertical wire
                    pts = [
                        (start_x, start_y),
                        (start_x + width, start_y),
                        (start_x + width, start_y + length),
                        (start_x, start_y + length)
                    ]
                synthetic_boundaries.append({
                    "layer": layer,
                    "name": name,
                    "z": z,
                    "points": pts
                })
        export_to_obj(synthetic_boundaries, obj_out)
    else:
        boundaries = parse_gdsii(gds_in)
        if not boundaries:
            print("GDSII binary parse yielded 0 boundaries. Check if file is empty or using a different GDS record format.")
        export_to_obj(boundaries, obj_out)

if __name__ == "__main__":
    main()
