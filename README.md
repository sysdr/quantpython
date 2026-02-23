# AI Content Generator

This application is a powerful, multi-modal content creation tool powered by the Google Gemini API. It allows users to enter a single topic and generate a wide array of content, including scripts, audio podcasts, visual aids, explainer videos, and in-depth newsletter articles.

## ✨ Core Features

### 1. Multi-Format Content Generation
- **Script Writing**: Generate scripts in various formats:
  - **Podcast**: Conversational scripts for one or more speakers.
  - **Movie Script**: Scene-based scripts with character names and action lines.
  - **Monologue**: A single-speaker narrative.
- **Visual Aid Creation**: Automatically generate visuals to accompany the script:
  - **Illustrations & Photorealistic Images (JPEG)**: Create rich, raster-based images.
  - **SVG Diagrams**: Generate clean, scalable vector diagrams for technical topics.
  - **Pixel Art & Modern Illustrations**: Produce stylized visuals.
- **Audio Podcast Production**:
  - Utilizes the browser's Text-to-Speech engine to read the generated script aloud.
  - Features controls for playback, voice selection, speed, and pitch.
  - Allows recording the generated audio via screen capture for download.
- **Explainer Video Generation**:
  - Creates a short, engaging video based on the article's topic and a generated header image.
  - The process runs asynchronously, with status updates provided in the UI.
- **Newsletter Article Writing**:
  - Expands on the generated script to create a full-length, well-structured newsletter article in Markdown format.

### 2. Advanced Customization & Control
- **Dual Workflows**:
  - **Standard Content**: Directly generates a script and other assets from a topic.
  - **Technical Deep Dive**: A specialized workflow that first generates an in-depth article, extracts key concepts to create SVG diagrams, and then writes a final narration script based on both the text and the visuals.
- **Granular Topic & Tone Control**:
  - **Topic Category**: Choose from over 20 categories (e.g., "Technology," "Health & Wellness," "History") to frame the AI's perspective and ensure content relevance.
  - **Content Tone**: Select the desired tone, such as Informative, Humorous, Dramatic, or In-depth.
- **Fine-Tuning Parameters**:
  - **Content Length**: Control the approximate duration of the generated script.
  - **Number of Speakers**: Define how many speakers should be in the script.
  - **Language**: Generate content in over 10 languages.
  - **Creativity (Temperature)**: Adjust a slider to make the AI's output more predictable or more creative.
  - **Visuals**: Specify the number of images, image style, and aspect ratio (9:16 for mobile, 16:9 for video).

### 3. Interactive & User-Friendly Interface
- **Regeneration Options**: Independently regenerate the script or the visuals without starting over.
- **"Generate More" Visuals**: If the AI identifies more visual concepts than were initially generated, you can create more images with a single click.
- **Asset Downloads**:
  - Download all generated visuals (including both SVG and auto-converted PNG formats) as a single `.zip` file.
  - Download the generated video, recorded podcast audio, and newsletter text.
- **Responsive Design**: A clean, modern UI that works seamlessly across desktop and mobile devices.
- **Robust Error Handling**: Clear feedback for API errors, including authentication issues and rate limits.

---

## 🚀 User Workflows

### Standard Content Workflow
This is the most common workflow for generating general-purpose content.

1.  **Enter Topic**: The user inputs a topic (e.g., "The future of renewable energy").
2.  **Configure Options**:
    - Under "Advanced Options," the user selects a **Script Format** (e.g., "Podcast"), **Tone** (e.g., "Informative"), **Content Length**, and **Number of Speakers**.
    - The user can enable checkboxes to generate **Visuals**, an **Explainer Video**, and/or a **Newsletter Article**.
3.  **Generate**: The user clicks the "Generate" button.
4.  **Receive Content**: The application generates and displays:
    - The full script with speaker labels.
    - A header image and a gallery of additional visuals.
    - An in-depth newsletter article.
    - The user can then use the Podcast Controls to listen to an audio version of the script.
5.  **Video Generation (Optional)**: If selected, video generation begins in the background. The UI shows the current status (e.g., "Processing," "Complete") and provides a download link when ready.

### Technical Deep Dive Workflow
This workflow is designed for creating expert-level technical content with clear visual aids.

1.  **Enter Topic**: The user inputs a complex or technical topic (e.g., "How quantum computing works").
2.  **Select Workflow**: Under "Advanced Options," the user selects the **"Technical Deep Dive"** workflow. This automatically locks the visual type to SVG diagrams.
3.  **Configure Options**: The user sets the desired length, language, and number of speakers.
4.  **Generate**: The user clicks "Generate".
5.  **Receive Content**: The application performs a three-step process:
    - **Step 1 (Internal)**: Generates a detailed, long-form article on the topic.
    - **Step 2 (Internal)**: Analyzes the article to extract key visual concepts.
    - **Step 3 (Output)**: Generates a final narration script based on the article, along with a set of SVG diagrams visualizing the extracted concepts.
6.  **Review & Use**: The user is presented with the final script and the accompanying diagrams, ready for a presentation or technical explainer.

---

## 🛠️ Technology Stack

-   **Frontend**: React, TypeScript, Tailwind CSS
-   **AI Engine**: Google Gemini API (`@google/genai`)
    -   `gemini-2.5-flash` for text generation and analysis.
    -   `imagen-4.0-generate-001` for raster image generation.
    -   `veo-2.0-generate-001` for video generation.
-   **Utilities**:
    -   `jszip`: For bundling and downloading visual assets.
    -   `react-markdown`: For rendering the newsletter article.
    -   `esbuild`: Used in the `build` script for fast and efficient bundling.
# quantpython
