#!/usr/bin/env python3
import os
import sys
import time
import argparse
import subprocess
from dotenv import load_dotenv
from google import genai
from google.genai import types

def find_env_file():
    """Locate the .env file in .agents/ or .agent/ starting from current or parent directories."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Check current directory and its parent directory
    for parent in [current_dir, os.path.dirname(current_dir)]:
        for folder in ['.agents', '.agent']:
            path = os.path.join(parent, folder, '.env')
            if os.path.exists(path):
                return path
    return None

def clean_yaml_output(text: str) -> str:
    """Strip markdown code block fences if returned by the model."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text

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
    parser = argparse.ArgumentParser(description="Analyze video using Gemini API and the SEALCaM framework.")
    parser.add_argument("video_path", help="Path to the local video file to analyze.")
    parser.add_argument("-o", "--output", help="Optional path to save the YAML output.")
    parser.add_argument("-m", "--model", default="gemini-3.5-flash", help="Gemini model to use (default: gemini-3.5-flash).")
    
    args = parser.parse_args()
    
    # 1. Load environment variables
    env_path = find_env_file()
    if env_path:
        print(f"[*] Loading environment from {env_path}")
        load_dotenv(env_path)
    else:
        print("[!] No .env file found in .agents/ or .agent/. Using system environment variables.")

    video_path = os.path.abspath(args.video_path)
    if not os.path.exists(video_path):
        print(f"Error: Video file not found at {video_path}")
        sys.exit(1)

    # 2. Determine Authentication Mode
    api_key = os.environ.get("GEMINI_API_KEY")
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() in ("true", "1")
    
    client = None
    video_input = None
    gcs_uploaded_uri = None
    dev_api_file_name = None

    try:
        # If vertexai is preferred, or no Developer API Key is specified
        if use_vertex or not api_key:
            print("[*] Configuring GCP Vertex AI Authentication...")
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            
            if not project_id:
                # Attempt auto-detection using gcloud CLI
                try:
                    project_id = subprocess.check_output(
                        ["gcloud", "config", "get-value", "project"],
                        text=True,
                        stderr=subprocess.DEVNULL
                    ).strip()
                except Exception:
                    pass
            
            if not project_id:
                print("Error: GOOGLE_CLOUD_PROJECT environment variable is not set and default project could not be detected via gcloud CLI.")
                print("Please run 'gcloud auth login' and 'gcloud config set project <PROJECT_ID>', or define GOOGLE_CLOUD_PROJECT in your .agents/.env file.")
                sys.exit(1)

            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            gcs_bucket = os.environ.get("GCS_BUCKET")
            
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

            # Check if bucket exists, create if not
            print(f"[*] Checking if GCS bucket 'gs://{gcs_bucket}' exists...")
            check_bucket = subprocess.run(
                ["gcloud", "storage", "buckets", "describe", f"gs://{gcs_bucket}"],
                capture_output=True, text=True
            )
            if check_bucket.returncode != 0:
                print(f"[*] GCS bucket 'gs://{gcs_bucket}' does not exist. Creating bucket...")
                create_cmd = [
                    "gcloud", "storage", "buckets", "create", f"gs://{gcs_bucket}",
                    "--location", location,
                    "--default-storage-class", "STANDARD"
                ]
                create_bucket = subprocess.run(create_cmd, capture_output=True, text=True)
                if create_bucket.returncode != 0:
                    print(f"[!] Warning: Failed to create bucket 'gs://{gcs_bucket}': {create_bucket.stderr.strip()}")
                else:
                    print(f"[*] Successfully created bucket 'gs://{gcs_bucket}'.")
            else:
                print(f"[*] GCS bucket 'gs://{gcs_bucket}' exists.")

            # Upload using gcloud storage CLI
            gcs_uri = f"gs://{gcs_bucket}/temp_analyze_video/{os.path.basename(video_path)}"
            print(f"[*] Uploading video ({file_size_mb:.2f} MB) to GCS: {gcs_uri} ...")
            
            # Run gcloud storage cp
            upload_proc = subprocess.run(["gcloud", "storage", "cp", video_path, gcs_uri], capture_output=True, text=True)
            if upload_proc.returncode != 0:
                # Check if file size is small enough to pass inline as fallback
                if file_size_mb < 20:
                    print("[!] GCS upload failed. Fallback: Video is small enough (< 20MB) to pass inline.")
                    print("[*] Reading local video bytes...")
                    with open(video_path, "rb") as f:
                        video_bytes = f.read()
                    video_input = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
                else:
                    print(f"Error: GCS upload failed. Output:\n{upload_proc.stderr}")
                    print(f"Please check if the bucket '{gcs_bucket}' exists and your gcloud account has write access.")
                    sys.exit(1)
            else:
                print("[*] GCS upload successful.")
                gcs_uploaded_uri = gcs_uri
                video_input = types.Part.from_uri(file_uri=gcs_uri, mime_type="video/mp4")

            print(f"[*] Initializing Vertex AI client (Project: {project_id}, Location: {location})...")
            client = genai.Client(vertexai=True, project=project_id, location=location)

        else:
            # AI Studio Developer API Flow
            print("[*] Configuring AI Studio (Developer API) Authentication...")
            print("[*] Initializing Gemini client...")
            client = genai.Client(api_key=api_key)
            
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            print(f"[*] Uploading video ({file_size_mb:.2f} MB) to Gemini Developer File API...")
            video_file = client.files.upload(file=video_path)
            dev_api_file_name = video_file.name
            
            # Poll status until active
            print(f"[*] Uploaded as file name: {video_file.name}. Waiting for processing to complete...")
            while not video_file.state or video_file.state.name != "ACTIVE":
                state_str = video_file.state.name if video_file.state else "PROCESSING"
                print(f"[*] Current status: {state_str}. Retrying in 5 seconds...")
                time.sleep(5)
                video_file = client.files.get(name=video_file.name)
            
            print("[*] Video processing complete and ready.")
            video_input = video_file

        # 3. Analyze Video using SEALCaM
        print(f"[*] Sending analysis request to model: '{args.model}'...")
        prompt = """
You are an expert video director and AI video editor.
Analyze the uploaded video using the SEALCaM framework.
Break down the video scene-by-scene. A scene change occurs when there is a camera cut, transition, or major change in subject/environment.

For each scene, extract:
- Scene description: Brief narrative overview of what happens in the scene.
- Subject (S): The main focus or entity (e.g., product, character, object).
- Environment (E): The setting, backdrop, or context (e.g., indoor laboratory, forest at dusk).
- Action (A): The motion, actions, or gestures taking place.
- Lighting (L): The lighting setup, color palette, or conditions (e.g., high key, cinematic soft light).
- Camera (Ca): Camera characteristics (e.g., lens, focus, depth of field, zoom).
- Movement/Angle (M): Camera angle (e.g., low-angle, eye-level) and camera motion (e.g., panning, tracking, dolly).
- Approximate duration: Start and end timestamp or duration in seconds.

Also, capture a description of the background music, voiceover, sound effects, or overall audio style.

Output the entire analysis strictly in YAML format. Do not wrap the YAML output in Markdown code blocks (like ```yaml ... ```). Provide only the valid YAML text, using the exact schema below:

scenes:
  - scene_number: 1
    scene_description: "Scene description here"
    subject: "Subject description here"
    environment: "Environment description here"
    action: "Action description here"
    lighting: "Lighting style here"
    camera: "Camera characteristics here"
    movement_angle: "Camera angle and movement here"
    approximate_duration: "Duration here (e.g., 0:00 - 0:03)"
music_sound_description: "Music and sound description here"
"""
        response = client.models.generate_content(
            model=args.model,
            contents=[video_input, prompt]
        )
        
        yaml_text = clean_yaml_output(response.text)
        
        print("\n--- ANALYSIS RESULTS ---")
        print(yaml_text)
        print("------------------------\n")

        # 4. Save Output if Requested
        if args.output:
            output_path = os.path.abspath(args.output)
            # Create parent folder if not exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(yaml_text)
            print(f"[*] Successfully saved video analysis to: {output_path}")

    finally:
        # Cleanup temporary files
        if dev_api_file_name and client:
            print(f"[*] Cleaning up Developer File API: deleting '{dev_api_file_name}'...")
            try:
                client.files.delete(name=dev_api_file_name)
                print("[*] Cleanup successful.")
            except Exception as e:
                print(f"[!] Cleanup failed for '{dev_api_file_name}': {e}")
                
        if gcs_uploaded_uri:
            print(f"[*] Cleaning up temporary GCS video file: '{gcs_uploaded_uri}'...")
            try:
                subprocess.run(["gcloud", "storage", "rm", gcs_uploaded_uri], capture_output=True)
                print("[*] Cleanup successful.")
            except Exception as e:
                print(f"[!] Cleanup failed for GCS object: {e}")

if __name__ == "__main__":
    main()
