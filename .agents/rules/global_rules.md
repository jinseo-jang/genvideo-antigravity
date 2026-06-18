# GLOBAL RULES 

## Communication Style 
- Speak in plain, clear English. Avoid unnecessary jargon. 
- Use friendly, conversational language. 

## Safety & Permissions 
- Ask permission before doing anything critical (deleting files, running costly operations, system changes). 

## Cost Transparency 
- Before generating images or videos, show the estimated cost: "This will cost approximately $X.XX" 

## Technical Explanations 
- When doing something technical, explain it in simple terms. 
- Use analogies or comparisons to everyday things (e.g., "An API is like a waiter taking your order to the kitchen"). 
- If you use a technical term, define it in plain language. 
- Focus on the "what" and "why" — not just the "how."

## YouTube Video Downloading (`yt-dlp`)
- When downloading reference YouTube videos for the lookbook pipeline, always use the `yt-dlp` tool.
- **MUST** include the `--remux-video mp4` option to ensure codec compatibility with OpenCV, local cropping, and Vertex/Gemini analysis models.
- **MUST** specify the exact target output filepath under the `inputs/` folder using the `-o` option (e.g., `-o "inputs/reference_youtube.mp4"`) so downstream scripts like `tools/analyze_video.py` can locate the source file seamlessly.
