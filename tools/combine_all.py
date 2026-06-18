#!/usr/bin/env python3
import os
import sys
import glob
import re
import argparse
import subprocess

def get_scene_num(filepath):
    """Extract scene number from the filename to sort them numerically."""
    basename = os.path.basename(filepath)
    match = re.search(r'generated_scene_(\d+)', basename)
    return int(match.group(1)) if match else 9999

def get_video_duration(video_path):
    """Retrieve video duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    try:
        output = subprocess.check_output(cmd, text=True).strip()
        return float(output)
    except Exception as e:
        print(f"[!] Warning: Could not detect video duration using ffprobe: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Combine multiple video clips into one final video using FFmpeg.")
    parser.add_argument("-i", "--inputs", nargs="+", help="List of video file paths to concatenate. If omitted, they are auto-discovered from the outputs/ folder.")
    parser.add_argument("-o", "--output", help="Path to save the final video.")
    parser.add_argument("-m", "--music", help="Optional path to a background music file to overlay.")
    
    args = parser.parse_args()
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outputs_dir = os.path.join(project_root, "outputs")
    
    # 1. Determine Output Path
    output_path = args.output
    if not output_path:
        output_path = os.path.join(outputs_dir, "final_video.mp4")
    else:
        output_path = os.path.abspath(output_path)
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 2. Discover Input Videos
    input_files = []
    if args.inputs:
        for p in args.inputs:
            input_files.append(os.path.abspath(p))
    else:
        # Auto-discover outputs/generated_scene_*_composite.mp4
        pattern = os.path.join(outputs_dir, "generated_scene_*_composite.mp4")
        discovered = glob.glob(pattern)
        
        # Fallback to outputs/generated_scene_*_merged.mp4 if no _composite found
        if not discovered:
            pattern_merged = os.path.join(outputs_dir, "generated_scene_*_merged.mp4")
            discovered = glob.glob(pattern_merged)
            
        # Fallback to outputs/generated_scene_*.mp4 if neither found
        if not discovered:
            pattern_fallback = os.path.join(outputs_dir, "generated_scene_*.mp4")
            discovered = [
                f for f in glob.glob(pattern_fallback)
                if "uncropped" not in f and "temp" not in f and "final" not in f
            ]
            
        input_files = sorted(discovered, key=get_scene_num)
        
    if not input_files:
        print("[!] Error: No input video files found.")
        print("Please specify input paths using --inputs, or ensure generated video scenes exist in outputs/.")
        sys.exit(1)
        
    print(f"[*] Found {len(input_files)} video clips to concatenate:")
    for idx, f in enumerate(input_files):
        print(f"  [{idx + 1}] {os.path.basename(f)}")
        
    # Check if FFmpeg is installed
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("[!] Error: FFmpeg is not installed on this system.")
        sys.exit(1)
        
    # 3. Create videos.txt listing all files
    list_txt_path = os.path.join(project_root, "videos.txt")
    print(f"[*] Creating temporary concat list at {list_txt_path} ...")
    try:
        with open(list_txt_path, "w", encoding="utf-8") as f:
            for filepath in input_files:
                # Use absolute paths and escape single quotes for FFmpeg concat demuxer
                escaped_path = filepath.replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
    except Exception as e:
        print(f"[!] Error creating file list: {e}")
        sys.exit(1)
        
    # 4. Concatenate videos
    temp_combined_path = os.path.join(outputs_dir, "temp_combined.mp4")
    print(f"[*] Concatenating video clips into temporary file {temp_combined_path} ...")
    
    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_txt_path, "-c", "copy", temp_combined_path
    ]
    
    try:
        subprocess.run(concat_cmd, check=True)
        print("[+] Concatenation completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[!] Error: FFmpeg concatenation failed: {e}")
        # Clean up
        if os.path.exists(list_txt_path):
            os.remove(list_txt_path)
        sys.exit(1)
        
    # 5. Optional Music Overlay & Fade Out
    if args.music:
        music_path = os.path.abspath(args.music)
        if not os.path.exists(music_path):
            print(f"[!] Warning: Background music file not found at {music_path}.")
            print(f"[*] Saving concatenated video directly without audio to {output_path} ...")
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_combined_path, output_path)
        else:
            print(f"[*] Overlaying background music {os.path.basename(music_path)} ...")
            duration = get_video_duration(temp_combined_path)
            
            audio_filter = ""
            if duration:
                fade_start = max(0.0, duration - 2.0)
                audio_filter = f"afade=t=out:st={fade_start}:d=2"
                print(f"[*] Calculated video duration: {duration:.2f}s. Audio fade-out will start at {fade_start:.2f}s.")
            else:
                print("[!] Could not determine duration. Overlaying music without fade-out...")
                
            music_cmd = [
                "ffmpeg", "-y", "-i", temp_combined_path, "-i", music_path,
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac"
            ]
            
            if audio_filter:
                music_cmd.extend(["-af", audio_filter])
                
            music_cmd.extend(["-shortest", output_path])
            
            print("[*] Running FFmpeg overlay command...")
            try:
                subprocess.run(music_cmd, check=True)
                print(f"[+] Final video with audio saved to {output_path}")
            except subprocess.CalledProcessError as e:
                print(f"[!] Error: FFmpeg music overlay failed: {e}")
                print(f"[*] Saving concatenated video without music to {output_path} ...")
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_combined_path, output_path)
            finally:
                if os.path.exists(temp_combined_path):
                    os.remove(temp_combined_path)
    else:
        # Save directly
        print(f"[*] No background music specified. Saving final video to {output_path} ...")
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_combined_path, output_path)
        
    # 6. Cleanup
    if os.path.exists(list_txt_path):
        os.remove(list_txt_path)
    print("[+] Cleanup complete.")
    print(f"🎉 Final combined video generated successfully at: {output_path}")

if __name__ == "__main__":
    main()
