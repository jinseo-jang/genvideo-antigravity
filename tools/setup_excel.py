#!/usr/bin/env python3
import os
import sys
import json
import re
import xlsxwriter

def load_simple_yaml(path: str) -> list:
    """A lightweight, zero-dependency parser for our specific scenes YAML file."""
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    scenes = []
    current_scene = {}
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Check if line indicates a new scene item
        if line.startswith('- scene_number:') or line.startswith('scene_number:'):
            if current_scene:
                scenes.append(current_scene)
                current_scene = {}
            match = re.search(r'\d+', line)
            if match:
                current_scene['scene_number'] = int(match.group())
        elif line.startswith('image_prompt:'):
            val = line.split('image_prompt:', 1)[1].strip()
            # Remove enclosing quotes if present
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            current_scene['image_prompt'] = val
        elif line.startswith('video_prompt:'):
            val = line.split('video_prompt:', 1)[1].strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            current_scene['video_prompt'] = val
            
    if current_scene:
        scenes.append(current_scene)
    return scenes

def find_env_file():
    """Locate the .env file in .agents/ or .agent/ starting from current or parent directories."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for parent in [current_dir, os.path.dirname(current_dir)]:
        for folder in ['.agents', '.agent']:
            path = os.path.join(parent, folder, '.env')
            if os.path.exists(path):
                return path
    return None

def write_excel_from_json(data_path: str, excel_path: str):
    """Read the JSON database and generate a styled Excel sheet using xlsxwriter."""
    if not os.path.exists(data_path):
        print(f"Error: JSON data file not found at {data_path}")
        return

    with open(data_path, 'r', encoding='utf-8') as f:
        db = json.load(f)

    project_name = db.get("project_name", "Coca-Cola Branding Video")
    scenes = db.get("scenes", [])

    print(f"[*] Generating Excel tracker: {excel_path} ...")
    
    # Create workbook and sheet
    workbook = xlsxwriter.Workbook(excel_path)
    worksheet = workbook.add_worksheet("Scenes")

    # Set column widths
    worksheet.set_column('A:A', 25) # Project Name
    worksheet.set_column('B:B', 15) # Scene
    worksheet.set_column('C:C', 50) # start_image_prompt
    worksheet.set_column('D:D', 50) # video_prompt
    worksheet.set_column('E:E', 35) # start_image
    worksheet.set_column('F:F', 35) # scene_video

    # Define text formatting styles
    header_format = workbook.add_format({
        'bold': True,
        'font_color': 'white',
        'bg_color': '#E31B23', # Coca-Cola Red!
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })
    
    cell_format = workbook.add_format({
        'text_wrap': True,
        'valign': 'top',
        'border': 1
    })

    # Write headers
    headers = [
        "Project Name",
        "scene",
        "start_image_prompt",
        "video_prompt",
        "start_image",
        "scene_video"
    ]
    for col_idx, header in enumerate(headers):
        worksheet.write(0, col_idx, header, header_format)
    worksheet.set_row(0, 25) # Make header row taller

    # Write data rows
    for row_idx, scene in enumerate(scenes, start=1):
        worksheet.write(row_idx, 0, project_name, cell_format)
        worksheet.write(row_idx, 1, f"Scene {scene.get('scene_number')} - {scene.get('scene_name', 'Scene')}", cell_format)
        worksheet.write(row_idx, 2, scene.get("start_image_prompt", ""), cell_format)
        worksheet.write(row_idx, 3, scene.get("video_prompt", ""), cell_format)
        worksheet.write(row_idx, 4, scene.get("start_image", ""), cell_format)
        worksheet.write(row_idx, 5, scene.get("scene_video", ""), cell_format)
        worksheet.set_row(row_idx, 80) # Make data rows tall enough for long prompts

    workbook.close()
    print("[*] Excel tracker closed and saved successfully.")

def main():
    # Paths definition
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yaml_path = os.path.join(project_root, "outputs", "scenes_prompts.yaml")
    json_path = os.path.join(project_root, "outputs", "project_data.json")
    excel_path = os.path.join(project_root, "outputs", "project_tracker.xlsx")

    # 1. Load prompts from YAML if exists
    if os.path.exists(yaml_path):
        print(f"[*] Reading prompts from {yaml_path} ...")
        yaml_scenes = load_simple_yaml(yaml_path)
    else:
        print(f"[!] Warning: Prompts file not found at {yaml_path}. Using hardcoded default prompts.")
        yaml_scenes = []

    # 2. Build database structure
    scenes_db = []
    
    # We map YAML scenes to our JSON schema
    if yaml_scenes:
        for s in yaml_scenes:
            scenes_db.append({
                "scene_number": s.get("scene_number", 1),
                "scene_name": "Outdoor Coca-Cola Can Clone",
                "start_image_prompt": s.get("image_prompt", ""),
                "video_prompt": s.get("video_prompt", ""),
                "start_image": "",
                "scene_video": ""
            })
    else:
        # Hardcoded default values if yaml file is missing
        scenes_db.append({
            "scene_number": 1,
            "scene_name": "Outdoor Coca-Cola Can Clone",
            "start_image_prompt": "A professional product photograph of a sleek, tall 250ml Coca-Cola red aluminum can with the white script logo, sitting upright on the dry dirt ground outdoors.",
            "video_prompt": "A low-angle, stationary shot of the Coca-Cola can sitting on the dirt ground. Condensation forms on the glossy red metal surface...",
            "start_image": "",
            "scene_video": ""
        })

    db_data = {
        "project_name": "Coca-Cola Branding Video",
        "scenes": scenes_db
    }

    # Save to JSON database
    print(f"[*] Saving JSON database to {json_path} ...")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(db_data, f, indent=2, ensure_ascii=False)

    # 3. Write Excel from the JSON database
    write_excel_from_json(json_path, excel_path)

if __name__ == "__main__":
    main()
