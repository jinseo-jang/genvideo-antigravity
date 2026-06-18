#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
import urllib.parse
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Add tools directory to path to import setup_excel
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from setup_excel import write_excel_from_json, find_env_file
from generate_images import get_gcs_headers, ensure_gcs_bucket, upload_to_gcs, update_env_file

def parse_xlsx_tracker(excel_path):
    """Parse outputs/project_tracker.xlsx to find scenes and their current states without openpyxl."""
    import zipfile
    import xml.etree.ElementTree as ET
    import re

    if not os.path.exists(excel_path):
        print(f"[!] Tracker spreadsheet not found at {excel_path}")
        return []
        
    print(f"[*] Reading project tracker from {excel_path} ...")
    scenes = []
    
    try:
        with zipfile.ZipFile(excel_path) as z:
            # Load shared strings
            strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                root = ET.fromstring(z.read('xl/sharedStrings.xml'))
                ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in root.findall('ns:si', ns):
                    t = si.find('ns:t', ns)
                    strings.append(t.text if t is not None else '')
                    
            # Load sheet1
            sheet = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            
            rows = sheet.findall('.//ns:row', ns)
            if not rows:
                return []
                
            # Parse header row to find column mapping
            header_cells = rows[0].findall('ns:c', ns)
            headers = {}
            for i, c in enumerate(header_cells):
                val = c.find('ns:v', ns)
                val_text = val.text if val is not None else ''
                if c.get('t') == 's':
                    val_text = strings[int(val_text)] if val_text.isdigit() else val_text
                headers[val_text] = i
                
            # Column indices
            proj_col = headers.get("Project Name")
            scene_col = headers.get("scene")
            prompt_col = headers.get("video_prompt")
            img_col = headers.get("start_image")
            video_col = headers.get("scene_video")
            
            # Parse rows
            for row in rows[1:]:
                cells = row.findall('ns:c', ns)
                row_data = [None] * (max(headers.values()) + 1)
                for c in cells:
                    ref = c.get('r')
                    col_letter = ''.join([x for x in ref if x.isalpha()])
                    col_idx = 0
                    for char in col_letter:
                        col_idx = col_idx * 26 + (ord(char.upper()) - ord('A') + 1)
                    col_idx -= 1
                    
                    val = c.find('ns:v', ns)
                    val_text = val.text if val is not None else ''
                    if c.get('t') == 's':
                        val_text = strings[int(val_text)] if val_text.isdigit() else val_text
                    if col_idx < len(row_data):
                        row_data[col_idx] = val_text
                        
                proj_name = row_data[proj_col] if proj_col is not None else ""
                scene_str = row_data[scene_col] if scene_col is not None else ""
                video_prompt = row_data[prompt_col] if prompt_col is not None else ""
                start_image = row_data[img_col] if img_col is not None else ""
                scene_video = row_data[video_col] if video_col is not None else ""
                
                if proj_name or scene_str:
                    scene_num = 1
                    num_match = re.search(r'\d+', scene_str)
                    if num_match:
                        scene_num = int(num_match.group())
                        
                    scenes.append({
                        "project_name": proj_name,
                        "scene_str": scene_str,
                        "scene_number": scene_num,
                        "video_prompt": video_prompt,
                        "start_image": start_image,
                        "scene_video": scene_video
                    })
    except Exception as e:
        print(f"[!] Error parsing Excel tracker: {e}")
        return []
        
    return scenes

def download_from_gcs(bucket_name, object_name, local_dest):
    """Download a file from GCS using the JSON API."""
    headers, _ = get_gcs_headers()
    quoted_obj = urllib.parse.quote(object_name, safe='')
    url = f"https://storage.googleapis.com/storage/v1/b/{bucket_name}/o/{quoted_obj}?alt=media"
    
    print(f"[*] Downloading gs://{bucket_name}/{object_name} to {local_dest} ...")
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        os.makedirs(os.path.dirname(os.path.abspath(local_dest)), exist_ok=True)
        with open(local_dest, 'wb') as f:
            f.write(resp.content)
        print(f"[+] Download completed: {local_dest}")
    else:
        raise Exception(f"Failed to download from GCS: {resp.text}")

def generate_video_with_fallback(client_args, prompt, config):
    """Initiate video generation by trying Veo models in a fallback sequence."""
    models = ['veo-2.0-generate-001', 'veo-3.1-generate-preview']
    last_err = None
    
    # Force us-central1 as Veo is typically only available in us-central1
    current_args = client_args.copy()
    current_args['location'] = 'us-central1'
    
    print(f"[*] Initializing Vertex AI client in location: {current_args['location']}...")
    client = genai.Client(**current_args)
    
    for model in models:
        print(f"[*] Requesting video generation using model '{model}'...")
        try:
            operation = client.models.generate_videos(
                model=model,
                prompt=prompt,
                config=config
            )
            print(f"[+] Success! Initiated video generation with model '{model}'.")
            return client, operation
        except Exception as e:
            last_err = e
            print(f"[!] Model '{model}' failed: {e}")
            
    raise last_err

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(project_root, "outputs", "project_data.json")
    excel_path = os.path.join(project_root, "outputs", "project_tracker.xlsx")

    # 1. Load environment variables
    env_path = find_env_file()
    if env_path:
        print(f"[*] Loading environment from {env_path}")
        load_dotenv(env_path)
    else:
        print("[!] Warning: .env file not found. Using system environment variables.")

    # 2. Get GCP Configurations
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        try:
            _, resolved_project_id = get_gcs_headers()
            project_id = resolved_project_id
        except Exception:
            pass
            
    if not project_id:
        import subprocess
        try:
            project_id = subprocess.check_output(
                ["gcloud", "config", "get-value", "project"],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            pass

    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    gcs_bucket = os.environ.get("GCS_BUCKET")

    if not project_id:
        print("Error: GOOGLE_CLOUD_PROJECT is not set and could not be detected.")
        sys.exit(1)

    # Prompt user for GCS bucket name if missing
    if not gcs_bucket or not gcs_bucket.strip():
        print("[!] GCS_BUCKET is not set in your .agents/.env file.")
        gcs_bucket = input("Please enter GCS bucket name: ").strip()
        while not gcs_bucket:
            gcs_bucket = input("GCS bucket name cannot be empty. Please enter GCS bucket name: ").strip()
        
        if env_path:
            try:
                update_env_file(env_path, "GCS_BUCKET", gcs_bucket)
            except Exception as e:
                print(f"[!] Warning: Failed to save GCS_BUCKET to .env: {e}")

    # 3. Read excel tracker
    excel_scenes = parse_xlsx_tracker(excel_path)
    if not excel_scenes:
        print("[!] No scenes parsed from Excel tracker. Make sure outputs/project_tracker.xlsx exists.")
        sys.exit(1)

    # Filter scenes that need video generation (has start_image but no scene_video)
    scenes_to_generate = []
    for s in excel_scenes:
        if s.get("start_image") and not s.get("scene_video"):
            scenes_to_generate.append(s)

    if not scenes_to_generate:
        print("[*] No scenes need video generation (either start_image is missing, or scene_video is already generated).")
        sys.exit(0)

    # 4. Display Cost and Ask for User Approval
    num_videos = len(scenes_to_generate)
    total_seconds = num_videos * 8
    estimated_cost = total_seconds * 0.40 # Standard quality Veo is ~$0.40/second
    
    print(f"\n==================================================")
    print(f"💰 ESTIMATED COST")
    print(f"This will generate {num_videos} video(s) ({total_seconds} seconds total) using Veo latest model.")
    print(f"Estimated cost: ~${estimated_cost:.2f} total (at approx $0.40/sec). Ready to proceed?")
    print(f"==================================================")
    
    if "--yes" in sys.argv or "-y" in sys.argv:
        print("[*] Automatically confirmed via command line flag.")
    else:
        confirm = input("Confirm (y/n): ").strip().lower()
        if confirm not in ('y', 'yes'):
            print("[*] Video generation cancelled by user.")
            sys.exit(0)

    # 5. Ensure Bucket Exists
    ensure_gcs_bucket(gcs_bucket, location)

    # 6. Generate Videos
    client_args = {
        'vertexai': True,
        'project': project_id,
        'location': location
    }

    # Load JSON database to update it later
    if not os.path.exists(json_path):
        print(f"Error: Project database not found at {json_path}")
        sys.exit(1)

    with open(json_path, 'r', encoding='utf-8') as f:
        db = json.load(f)

    for idx, scene in enumerate(scenes_to_generate):
        scene_num = scene.get('scene_number', 1)
        scene_id = scene.get('scene_str', f"Scene {scene_num}")
        video_prompt = scene.get("video_prompt")
        start_image = scene.get("start_image")
        
        print(f"\n[*] Step 2: Generating video for '{scene_id}'...")
        print(f"[*] Prompt: \"{video_prompt[:120]}...\"")
        print(f"[*] Reference Image URL: {start_image}")
        
        # Convert start_image public or authenticated URL to GCS URI
        ref_gcs_uri = start_image
        if start_image.startswith("https://storage.googleapis.com/"):
            parts = start_image[len("https://storage.googleapis.com/"):].split("/", 1)
            ref_gcs_uri = f"gs://{parts[0]}/{parts[1]}"
        elif start_image.startswith("https://storage.cloud.google.com/"):
            parts = start_image[len("https://storage.cloud.google.com/"):].split("/", 1)
            ref_gcs_uri = f"gs://{parts[0]}/{parts[1]}"
            
        print(f"[*] Using starting image GCS URI: {ref_gcs_uri}")

        # Configure video generation cascade
        # Format: (aspect_ratio, resolution, crop_needed)
        configs_to_try = [
            ("9:16", "1080p", False),
            ("9:16", "720p", False),
            ("16:9", "1080p", True),
            ("16:9", "720p", True)
        ]
        video_data = None
        crop_needed = False
        
        for aspect_ratio, res, crop in configs_to_try:
            print(f"[*] Attempting video generation with aspect_ratio={aspect_ratio}, resolution={res} (crop_needed={crop})...")
            config = types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                resolution=res,
                duration_seconds=8,
                reference_images=[
                    types.VideoGenerationReferenceImage(
                        image=types.Image(gcs_uri=ref_gcs_uri, mime_type="image/png"),
                        reference_type="asset"
                    )
                ]
            )

            try:
                # Initiate video generation
                client, operation = generate_video_with_fallback(client_args, video_prompt, config)
                
                # Poll operation
                start_time = time.time()
                print("[*] Polling video generation status (can take 2-4 minutes)...")
                while not operation.done:
                    elapsed = int(time.time() - start_time)
                    print(f"[*] Polling video generation... (Elapsed: {elapsed}s)")
                    time.sleep(20)
                    operation = client.operations.get(operation)
                    
                print(f"[+] Video generation completed in {int(time.time() - start_time)}s.")
                
                if operation.error:
                    err_msg = str(operation.error)
                    print(f"[!] Operation finished with error: {err_msg}")
                    # If it's an aspect ratio error, fall back to next config
                    if "aspect ratio" in err_msg.lower() or "aspect_ratio" in err_msg.lower() or "unsupported" in err_msg.lower():
                        print("[!] Aspect ratio/Resolution unsupported by this model. Trying next configuration...")
                        continue
                    else:
                        raise Exception(f"Video generation operation failed: {operation.error}")
                
                if not operation.response or not operation.response.generated_videos:
                    raise Exception("No generated video found in operation response.")
                    
                generated_video = operation.response.generated_videos[0]
                video_data = generated_video.video
                crop_needed = crop
                break # Successfully generated video, break loop
                
            except Exception as e:
                err_msg = str(e)
                print(f"[!] Caught exception during generation/polling: {err_msg}")
                if "aspect ratio" in err_msg.lower() or "aspect_ratio" in err_msg.lower() or "unsupported" in err_msg.lower() or "400" in err_msg.lower():
                    print("[!] Aspect ratio/Resolution unsupported. Trying next configuration...")
                    continue
                else:
                    raise e
                    
        if not video_data:
            print(f"[!] Error: Video generation failed for '{scene_id}': No video data generated after trying all configurations.")
            continue
            
        local_out_name = f"generated_scene_{scene_num}_composite.mp4"
        local_out_path = os.path.join(project_root, "outputs", local_out_name)
        os.makedirs(os.path.dirname(local_out_path), exist_ok=True)
            
        target_download_path = local_out_path
        if crop_needed:
            target_download_path = os.path.join(project_root, "outputs", f"generated_scene_{scene_num}_composite_uncropped.mp4")
            
        if video_data.video_bytes:
            # Save bytes directly
            print(f"[*] Saving video bytes locally to {target_download_path} ...")
            with open(target_download_path, 'wb') as f:
                f.write(video_data.video_bytes)
            print("[+] Saved video bytes locally.")
        elif video_data.uri:
            # Fallback to downloading GCS URI
            print(f"[*] Video output uri: {video_data.uri}")
            if not video_data.uri.startswith("gs://"):
                raise Exception(f"Invalid output video URI returned: {video_data.uri}")
            parts = video_data.uri[5:].split("/", 1)
            out_bucket = parts[0]
            out_obj_path = parts[1]
            download_from_gcs(out_bucket, out_obj_path, target_download_path)
        else:
            raise Exception("Neither video bytes nor output URI was returned.")

        if crop_needed:
            # Run FFmpeg locally to crop the center 9:16 portrait area
            import subprocess
            print(f"[*] Cropping uncropped video {target_download_path} to 9:16 aspect ratio: {local_out_path} ...")
            try:
                # Crop command: ffmpeg -y -i input.mp4 -vf "crop=floor(in_h*9/16/2)*2:in_h" -c:a copy output.mp4
                cmd = [
                    "ffmpeg", "-y", "-i", target_download_path,
                    "-vf", "crop=floor(in_h*9/16/2)*2:in_h",
                    "-c:a", "copy",
                    local_out_path
                ]
                subprocess.run(cmd, check=True)
                print("[+] Video cropped successfully using FFmpeg.")
                # Clean up temporary uncropped video
                if os.path.exists(target_download_path):
                    os.remove(target_download_path)
            except Exception as e:
                print(f"[!] Error cropping video with FFmpeg: {e}")
                print(f"[*] Falling back to using the uncropped video: {local_out_path}")
                if os.path.exists(target_download_path):
                    if os.path.exists(local_out_path):
                        os.remove(local_out_path)
                    os.rename(target_download_path, local_out_path)
        
        # Upload clean video to GCS with the desired filename
        clean_gcs_obj = f"outputs/{local_out_name}"
        upload_to_gcs(local_out_path, gcs_bucket, clean_gcs_obj, content_type='video/mp4')
        
        # Set authenticated GCS URL for browser access
        authenticated_gcs_url = f"https://storage.cloud.google.com/{gcs_bucket}/{clean_gcs_obj}"
        
        # Update database
        for s in db.get("scenes", []):
            if s.get("scene_number") == scene_num:
                s["scene_video"] = authenticated_gcs_url
                print(f"[+] Updated JSON database with authenticated GCS URL: {authenticated_gcs_url}")
                break

    # 7. Write Database Back to File & Update Excel
    print(f"\n[*] Step 3: Saving results to database and updating Excel sheet...")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
        
    write_excel_from_json(json_path, excel_path)
    print("🎉 Video generation completed successfully!")

if __name__ == "__main__":
    main()
