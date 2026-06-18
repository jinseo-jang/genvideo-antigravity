# Project Context & Specification

## 1. Project Overview
- **Description**: A project designed to automate the generation of branding videos.
- **Goal**: Utilize Antigravity 2.0 to orchestrate video generation workflows, leveraging the latest Veo models for high-quality video synthesis and Gemini Nano Banana models for reasoning, scenario planning, and content automation.

## 2. Tech Stack & Dependencies
- **Programming Language**: Python
- **Orchestration / SDK**: Antigravity 2.0
- **AI Models**:
  - Veo (latest models for video generation)
  - Gemini Nano Banana (latest models for prompt/scenario generation and text-based reasoning)
- **Media Processing**: FFmpeg (for video composition, stitching, formatting, and rendering)
- **Integrations / Storage**: Google Workspace (Google Drive, Docs, Sheets, etc., for asset management and distribution)

## 3. Directory Structure
- Consolidated project structure:
  ```
  .
  ├── .agents/                 # Workspace customizations & configuration root (Antigravity 2.0)
  │   ├── project_context.md   # Project context & architecture specification (this file)
  │   ├── rules/               # Workspace rules (e.g. global_rules.md)
  │   ├── skills/              # Project-specific custom agent skills
  │   ├── workflows/           # Predefined workflows
  │   └── .env                 # API keys environment file (empty by default)
  ├── inputs/                  # Reference videos and photos
  ├── outputs/                 # Generated images, videos, and music
  └── tools/                   # Helper scripts (e.g. analyze_video.py)
  ```

## 4. Core Logic & Algorithms
- **Scenario Planning**: Leveraging Gemini Nano Banana to parse branding inputs and design creative video outlines/prompts.
- **Video Generation**: Generating high-fidelity visual assets using the Veo API based on generated prompts.
- **Video Assembly**: Using FFmpeg wrapper scripts to compile video clips, add audio overlays, and apply transitions.
- **Workflow Automation**: Automating the entire pipeline from asset acquisition (via Google Workspace) to final video storage using Antigravity 2.0 agents.

## 5. Coding Conventions
- **Language Style**: Clean, idiomatic Python following PEP 8.
- **Simplicity & SRP**: Each class and function must do one thing (Single Responsibility Principle). Keep functions small and dense.
- **API & Integrations**: Decouple integrations with design patterns like dependency injection for APIs (Veo, Gemini, Workspace).
- **Error Handling**: Robust exception handling around external API calls (especially rate limits, network timeouts).
