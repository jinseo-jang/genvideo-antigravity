#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Add tools directory to path to import setup_excel
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from setup_excel import write_excel_from_json, find_env_file

def get_gcs_headers():
    """Obtain credentials using application default credentials (ADC) and return headers for GCS API."""
    import google.auth
    from google.auth.transport.requests import Request
    credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/devstorage.full_control'])
    credentials.refresh(Request())
    return {
        'Authorization': f'Bearer {credentials.token}'
    }, project

def ensure_gcs_bucket(bucket_name, location):
    """Ensure that the GCS bucket exists. If not, create it."""
    headers, project_id = get_gcs_headers()
    url = f"https://storage.googleapis.com/storage/v1/b/{bucket_name}"
    
    print(f"[*] Checking if GCS bucket 'gs://{bucket_name}' exists...")
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        print(f"[*] GCS bucket 'gs://{bucket_name}' exists.")
        return
        
    if resp.status_code == 404:
        print(f"[*] GCS bucket 'gs://{bucket_name}' does not exist. Creating bucket...")
        create_url = f"https://storage.googleapis.com/storage/v1/b?project={project_id}"
        payload = {
            "name": bucket_name,
            "location": location
        }
        create_resp = requests.post(create_url, headers=headers, json=payload)
        if create_resp.status_code == 200:
            print(f"[+] Successfully created bucket 'gs://{bucket_name}'.")
        else:
            raise Exception(f"Failed to create bucket: {create_resp.text}")
    else:
        raise Exception(f"Failed to check bucket existence: {resp.text}")

def upload_to_gcs(local_path, bucket_name, object_name, content_type='image/png'):
    """Upload a local file to GCS using the JSON API."""
    headers, _ = get_gcs_headers()
    upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket_name}/o?uploadType=media&name={object_name}"
    
    headers['Content-Type'] = content_type
    with open(local_path, 'rb') as f:
        data = f.read()
        
    print(f"[*] Uploading {local_path} to gs://{bucket_name}/{object_name} ...")
    resp = requests.post(upload_url, headers=headers, data=data)
    if resp.status_code == 200:
        print(f"[+] Upload succeeded.")
    elif resp.status_code == 403 and "retentionPolicyNotMet" in resp.text:
        print(f"[!] Warning: File gs://{bucket_name}/{object_name} is subject to a GCS retention policy and cannot be overwritten. Proceeding using the existing file.")
    else:
        raise Exception(f"Failed to upload to GCS: {resp.text}")

def generate_image_with_fallback(client_args, contents, config):
    """Generate image content by trying locations and models in a fallback sequence."""
    models = ['gemini-3.1-flash-image', 'gemini-2.5-flash-image']
    locations = [client_args.get('location'), 'us-central1']
    
    # Remove duplicates from locations while keeping order
    seen = set()
    locations = [x for x in locations if x and not (x in seen or seen.add(x))]
    
    last_err = None
    for loc in locations:
        current_args = client_args.copy()
        current_args['location'] = loc
        print(f"[*] Initializing Vertex AI client in location: {loc}...")
        client = genai.Client(**current_args)
        
        for model in models:
            print(f"[*] Requesting generation using model '{model}'...")
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                print(f"[+] Success! Generated image with '{model}' in '{loc}'.")
                return response
            except Exception as e:
                last_err = e
                print(f"[!] Model '{model}' failed in location '{loc}': {e}")
                
    raise last_err

def update_env_file(env_path, key, value):
    """Update a specific key in the .env file with the new value."""
    import re
    if not env_path or not os.path.exists(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if the key exists (e.g. GCS_BUCKET=)
    pattern = rf"^(\s*{key}\s*=)(.*)$"
    match = re.search(pattern, content, re.MULTILINE)
    
    if match:
        # Replace the value
        updated_content = re.sub(pattern, f"\\1{value}", content, flags=re.MULTILINE)
    else:
        # Append to the end
        if not content.endswith('\n'):
            content += '\n'
        updated_content = content + f"{key}={value}\n"
        
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    print(f"[*] Saved {key}={value} back to {env_path}")

def main():
    import re
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(project_root, "outputs", "project_data.json")
    excel_path = os.path.join(project_root, "outputs", "project_tracker.xlsx")
    ref_image_path = os.path.join(project_root, "inputs", "cola.png")

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
        # Try retrieving via google-auth
        try:
            _, resolved_project_id = get_gcs_headers()
            project_id = resolved_project_id
        except Exception:
            pass
            
    if not project_id:
        # Try retrieving via gcloud CLI
        import subprocess
        try:
            project_id = subprocess.check_output(
                ["gcloud", "config", "get-value", "project"],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            pass

    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-northeast1")
    gcs_bucket = os.environ.get("GCS_BUCKET")

    if not project_id:
        print("Error: GOOGLE_CLOUD_PROJECT is not set and could not be detected.")
        sys.exit(1)

    # If GCS_BUCKET is missing or empty, ask the user for it
    if not gcs_bucket or not gcs_bucket.strip():
        print("[!] GCS_BUCKET is not set in your .agents/.env file.")
        gcs_bucket = input("Please enter GCS bucket name: ").strip()
        while not gcs_bucket:
            gcs_bucket = input("GCS bucket name cannot be empty. Please enter GCS bucket name: ").strip()
        
        # Save it back to the .env file
        if env_path:
            try:
                update_env_file(env_path, "GCS_BUCKET", gcs_bucket)
            except Exception as e:
                print(f"[!] Warning: Failed to save GCS_BUCKET to .env: {e}")

    if not os.path.exists(ref_image_path):
        print(f"Error: Reference image not found at {ref_image_path}")
        print("Please make sure you have placed 'cola.png' in the 'inputs/' folder.")
        sys.exit(1)

    # 3. Read JSON database
    if not os.path.exists(json_path):
        print(f"Error: Project database not found at {json_path}")
        print("Please run 'python3 tools/setup_excel.py' first to initialize the database.")
        sys.exit(1)

    with open(json_path, 'r', encoding='utf-8') as f:
        db = json.load(f)

    project_name = db.get("project_name", "Coca-Cola Branding Video")
    scenes = db.get("scenes", [])
    if not scenes:
        print("Error: No scenes found in project database.")
        sys.exit(1)

    # 4. Display Cost and Ask for User Approval
    num_images = len(scenes)
    total_cost = num_images * 0.09
    
    print(f"\n==================================================")
    print(f"💰 ESTIMATED COST")
    print(f"This will generate {num_images} images at $0.09 each = ${total_cost:.2f} total. Ready to proceed?")
    print(f"==================================================")
    
    if "--yes" in sys.argv or "-y" in sys.argv:
        print("[*] Automatically confirmed via command line flag.")
    else:
        confirm = input("Confirm (y/n): ").strip().lower()
        if confirm not in ('y', 'yes'):
            print("[*] Image generation cancelled by user.")
            sys.exit(0)

    # 5. Ensure Bucket Exists and Upload Reference Image
    print(f"\n[*] Step 1: Uploading reference image to GCS bucket 'gs://{gcs_bucket}'...")
    ensure_gcs_bucket(gcs_bucket, location)
    
    ref_gcs_object = "reference_images/cola.png"
    ref_gcs_uri = f"gs://{gcs_bucket}/{ref_gcs_object}"
    upload_to_gcs(ref_image_path, gcs_bucket, ref_gcs_object, content_type='image/png')

    # 6. Generate Images and Save/Upload
    client_args = {
        'vertexai': True,
        'project': project_id,
        'location': location
    }

    for scene in scenes:
        scene_num = scene.get('scene_number', 1)
        scene_name = scene.get('scene_name', 'Scene')
        scene_id = f"Scene {scene_num} - {scene_name}"
        prompt = scene.get("start_image_prompt")
        
        print(f"\n[*] Step 2: Generating image for '{scene_id}'...")
        print(f"[*] Prompt: \"{prompt[:120]}...\"")
        
        # Prepare inputs
        ref_part = types.Part.from_uri(file_uri=ref_gcs_uri, mime_type="image/png")
        contents = [ref_part, prompt]
        
        # Configure image generation settings
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="9:16",
                image_size="2K"
            ),
        )
        
        try:
            # Generate the content using our fallback helper
            response = generate_image_with_fallback(client_args, contents, config)
            
            # Extract and save image bytes
            image_bytes = None
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    break
            
            if not image_bytes:
                print(f"[!] Warning: No image data returned in the response for '{scene_id}'")
                continue
                
            local_out_name = f"generated_scene_{scene_num}_composite.png"
            local_out_path = os.path.join(project_root, "outputs", local_out_name)
            
            os.makedirs(os.path.dirname(local_out_path), exist_ok=True)
            with open(local_out_path, 'wb') as f:
                f.write(image_bytes)
            print(f"[+] Saved generated image locally to {local_out_path}")
            
            # Upload generated image to GCS
            out_gcs_object = f"outputs/{local_out_name}"
            upload_to_gcs(local_out_path, gcs_bucket, out_gcs_object, content_type='image/png')
            
            # Form authenticated GCS URL for browser access
            authenticated_gcs_url = f"https://storage.cloud.google.com/{gcs_bucket}/{out_gcs_object}"
            
            # Update database record
            scene["start_image"] = authenticated_gcs_url
            print(f"[+] Scene record updated in JSON database with authenticated GCS URL: {authenticated_gcs_url}")
            
        except Exception as e:
            print(f"[!] Error: Image generation failed for '{scene_id}': {e}")
            continue

    # 7. Write Database Back to File & Update Excel
    print(f"\n[*] Step 3: Saving results to database and updating Excel sheet...")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
        
    write_excel_from_json(json_path, excel_path)
    print("🎉 All operations completed successfully!")

if __name__ == "__main__":
    main()
