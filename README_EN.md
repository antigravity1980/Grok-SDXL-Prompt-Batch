# Grok SDXL Prompt Batch 🚀

A professional-grade ComfyUI custom node package for batch prompt generation using **x.ai's Grok**. Designed for SDXL workflows, this package offers advanced LoRA intelligence, batch synchronization, and a premium image gallery.

## Features

- **Dual Generator Engines**:
  - **Grok SDXL Prompt Batch (Diverse)**: Mathematically enforces extreme subject diversity (cycles ages, ethnicities, hair, and body types automatically).
  - **Grok SDXL Prompt Batch (Identical)**: Strictly enforces semantic duplicates for consistent character generation.
- **Intelligent LoRA Selection**: Automatically identifies and applies the best LoRAs from your local folder based on the prompt's context.
- **LoRA Ecosystem**:
  - **Variant A (Auto-Text)**: AI selects models, you set the strength.
  - **Variant B (AI Strategy)**: AI selects models AND their ideal application strength.
- **V2 Batch Sync**: Automatically synchronizes your requested prompt count with ComfyUI's native batch counter (supports V1 and the new V2/1.39+ frontend).
- **Grok Image Saver (No Metadata)**: Securely saves your generation outputs while strictly stripping away all embedded ComfyUI workflow JSON metadata, protecting your proprietary settings.
- **Premium Gallery**: An interactive image grid with click-to-zoom history.

## Installation

1.  Clone this repository to your `ComfyUI/custom_nodes` folder:
    ```bash
    git clone https://github.com/antigravity1980/Grok-SDXL-Prompt-Batch.git
    ```
2.  Install requirements:
    ```bash
    pip install -r requirements.txt
    ```
3.  Restart ComfyUI.

## Configuration

Obtain your API key from [console.x.ai](https://console.x.ai/) and either:
- Set an environment variable `GROK_API_KEY`.
- (Optional) Create a file called `grok_api_key.txt` in the node's directory (excluded by .gitignore).

## Credits

- AI Logic powered by **x.ai (Grok)**.
- Built for the **ComfyUI** community.

---
*Developed for advanced agentic coding workflows.*
