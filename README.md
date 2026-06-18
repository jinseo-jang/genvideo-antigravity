# 📖 Developer Onboarding & Reusability Guide

Welcome to the **Creative Video Cloner** workspace! This guide is designed to help any team member, developer, or future Antigravity AI session clone this repository and immediately begin synthesizing high-end, customized branding videos.

By leveraging **Antigravity 2.0** and our packaged **Custom Skill**, the entire pipeline from video analysis to final lossless stitching can be orchestrated autonomously with a single user-facing request.

---

## 🛠️ 1. Prerequisites & Automated Environment Setup

If you are using **Antigravity 2.0**, you do **not** need to set up any environment variables, dependencies, or local system packages manually. The agent will run automated diagnostics as **Step 0** of the custom skill, performing the following checks and setup actions:

### 🤖 What Antigravity Autonomously Set Up for You:
1. **Installs System Dependencies**: Checks if `ffmpeg` is on your host's path. If missing, it requests permission and installs it autonomously via `brew install` (macOS) or `apt-get` (Linux).
2. **Installs Python Packages**: Automatically installs any missing libraries listed in `requirements.txt` (e.g. `pandas`, `google-genai`).
3. **Validates GCP Credentials**: Verifies if local credentials are set up. If not, it prompts you with instructions to login.
4. **Auto-Generates Configuration**: Searches for `.agents/.env`. If missing, it interactively asks for your GCP project ID, region, and GCS bucket name, and then creates the `.env` file for you automatically.

---

## ⚙️ 2. Manual Configuration (For Standard Non-AI Shell Run)

If you are **not** using Antigravity and wish to run the scripts manually in a traditional terminal session, please follow these setup instructions:

### Step 1: Install Local Dependencies
Ensure Python 3.10+ and FFmpeg are installed locally:
- **macOS**: `brew install ffmpeg`
- **Linux (Ubuntu/Debian)**: `sudo apt update && sudo apt install -y ffmpeg`

### Step 2: Configure Environment Variables
1. Create a `.env` file under the `.agents/` folder:
   ```bash
   touch .agents/.env
   ```
2. Paste and configure the following parameters:
   ```env
   GCP_PROJECT_ID="your-gcp-project-id"
   GCP_REGION="us-central1"
   GCS_BUCKET_NAME="your-gcs-bucket-name"
   ```

### Step 3: Local GCP Authentication
Ensure your local application credentials are active:
```bash
gcloud auth application-default login
```

> [!WARNING]
> Do **NOT** commit this `.env` file to version control. It is ignored by default in `.gitignore` to keep credentials secure.


---

## 🚀 3. How to Execute the Pipeline

You can run this project in two ways: **Option A (Autonomous Agent Mode - Recommended)** or **Option B (Manual Developer Mode)**.

---

### Option A: Autonomous Agent Mode (Recommended) 🤖
If you are pairing with an **Antigravity 2.0 Agent**, the agent will automatically discover the custom rules under `.agents/rules/global_rules.md` and the Custom Skill under `.agents/skills/creative-video-cloner/SKILL.md`.

You do not need to copy-paste or execute any terminal commands. Simply supply a reference video and your product image, and ask the agent to orchestrate the pipeline.

#### Example Prompts to Copy-Paste:
> **Prompt 1 (Using YouTube Link + Product Image):**
> "이 유튜브 링크 `https://youtube.com/shorts/FCepKLOM5A4`를 비디오 레퍼런스로 다운받고, 제품 이미지 `inputs/cola.png`를 조합해서 우리 브랜드 영상을 만들어줘. 프로젝트 커스텀 스킬(`creative-video-cloner`) 명세서를 참고해서 분석부터 합성, 크롭, 최종 병합까지 알아서 해줘."

> **Prompt 2 (Using Local Files):**
> "inputs/my_reference.mp4 비디오와 inputs/brand_shoe.png 이미지를 사용해서 커스텀 스킬에 정의된 시퀀스 다이어그램 순서대로 브랜드 마스터 비디오를 제작해줘. 시작하기 전에 예상 예산을 계산해서 승인받은 다음 동작해."

#### What Antigravity Does Behind the Scenes:
1. **Auto-downloads the video**: Uses `yt-dlp` with the workspace-mandated `--remux-video mp4` parameters and saves it directly to `inputs/reference_youtube.mp4`.
2. **Analyzes the Reference**: Triggers `analyze_video.py` to extract scene segments.
3. **Designs the Strategy**: Generates a unified prompt yaml matching the models to your product.
4. **Validates & Synthesizes**: Pauses at checkpoints to get your feedback on prompts/images, then runs the generation pipeline (`generate_images.py` -> `generate_videos.py` -> `combine_all.py`).

---

### Option B: Manual Developer Mode 💻
If you prefer executing the pipeline steps manually via your shell, execute the following commands in order:

#### Step 1: Download Reference Video
Download your reference clip using the mandated remux parameters:
```bash
yt-dlp --remux-video mp4 -o "inputs/reference_youtube.mp4" "https://youtube.com/shorts/FCepKLOM5A4"
```

#### Step 2: Analyze the Reference Video
Run the SEALCaM analysis tool to dissect the scene structures:
```bash
python3 tools/analyze_video.py inputs/reference_youtube.mp4 -o outputs/youtube_analysis.yaml
```

#### Step 3: Write Custom Prompts & Rebuild Tracker
1. Modify `outputs/scenes_prompts.yaml` with your custom composite scene strategies (modeling human subjects holding the target product as a prop).
2. Re-synchronize the JSON and Excel databases:
   ```bash
   python3 tools/setup_excel.py
   ```

#### Step 4: Generate 2K Starting Frames (Imagen 3)
```bash
python3 tools/generate_images.py
```
*Review the output images (e.g., `outputs/generated_scene_1_composite.png`) to ensure high-fidelity product integration before proceeding.*

#### Step 5: Synthesize Motion Videos (Veo)
```bash
python3 tools/generate_videos.py
```
*This automatically performs a 16:9 landscape fallback generation and crops it to portrait 9:16 using local FFmpeg.*

#### Step 6: Compile & Stitch Master Cut
```bash
python3 tools/combine_all.py --music inputs/background_track.mp3
```
*Your final, polished portrait branding video is compiled and saved to `outputs/final_video.mp4` with elegant transitions and audio fade-outs!*

---

## 📂 4. Pipeline Output Artifacts & Data Flow

As the pipeline runs from Step 1 to Step 6, a series of data structures, YAML states, and media files are generated and mutated under the `outputs/` folder. Understanding this data flow helps you audit, customize, or troubleshoot the branding video generation process.

### A. Stage-by-Stage Data Flow
1. **[Analysis Stage]**: `analyze_video.py` parses `inputs/reference_youtube.mp4` via Gemini Flash and writes scene intervals, visual subjects, lighting, and camera moves to `outputs/youtube_analysis.yaml`.
2. **[Database Initialization]**: `setup_excel.py` processes your custom composite prompt strategy inside `outputs/scenes_prompts.yaml` and initializes the main project database `outputs/project_data.json` and styled spreadsheet `outputs/project_tracker.xlsx`.
3. **[Image Synthesis]**: `generate_images.py` calls Imagen 3, saves high-quality starting frame images under `outputs/generated_scene_*_composite.png`, uploads them to Google Cloud Storage, and records their authenticated browser links back into `project_data.json` and `project_tracker.xlsx`.
4. **[Video Synthesis]**: `generate_videos.py` calls Veo, falls back to landscape 16:9 720p if needed, crops the viewport to portrait 9:16 using local FFmpeg, saves the final clip under `outputs/generated_scene_*_composite.mp4`, uploads it to GCS, and updates the database records with browser-accessible links.
5. **[Final Master Stitching]**: `combine_all.py` compiles the individual video clips into the final Master Video `outputs/final_video.mp4` with a background music overlay.

### B. Generated Artifacts Reference
| Filename | Created/Modified By | Format | Description & Purpose |
| :--- | :--- | :---: | :--- |
| `outputs/youtube_analysis.yaml` | `analyze_video.py` | YAML | Detailed SEALCaM scene-by-scene log extracted from the YouTube reference video. |
| `outputs/scenes_prompts.yaml` | User / Agent | YAML | Your central prompt blueprint. Modify this to refine how models and your product are synthesized together. |
| `outputs/project_data.json` | `setup_excel.py` / Generators | JSON | **The single source of truth (Database)**. Holds metadata, scene configurations, and browser-accessible GCS links. |
| `outputs/project_tracker.xlsx` | `setup_excel.py` / Generators | Excel | **User-facing progress dashboard** with custom Coca-Cola Red header styling, auto-wrapped cells, and clickable authenticated GCS URLs. |
| `outputs/generated_scene_N_composite.png` | `generate_images.py` | PNG | The 2K portrait starting frame for Scene N (with models holding/interacting with your product). |
| `outputs/generated_scene_N_composite.mp4` | `generate_videos.py` | MP4 | The animated, 8-second, 9:16 portrait video clip for Scene N, center-cropped locally using FFmpeg. |
| `outputs/final_video.mp4` | `combine_all.py` | MP4 | **The final master-cut branding video** (32 seconds, portrait 9:16 format, stitched with background music overlay and fade-out). |

---

## 🛑 5. Key Checkpoints & Guidelines to Keep in Mind

### 1. Cost Management & Transparency
| Action | Model | Est. Cost | Mode | Checkpoint Trigger |
| :--- | :--- | :---: | :---: | :--- |
| **Start Frame Synthesis** | Vertex AI Imagen 3 | \$0.09 per scene | Image | Approval of Starting Frame prompts in Tracker |
| **Motion Synthesis** | Vertex AI Veo | \$3.20 per scene | Video | Visual Quality Verification of Starting Frame PNGs |

### 2. GCS Overwrite Limitation
Due to strict Google Cloud Storage object retention policies, you cannot upload files with the exact same name as previously uploaded assets.
- **Rule**: Always preserve the `_composite` naming suffix. If you need to run another product line, create a sub-folder under `inputs/` or modify the suffix configuration to avoid write conflicts.

---

Have questions or run into issues? Create a Git issue or ask your **Antigravity 2.0** pair programming assistant for live troubleshooting!
