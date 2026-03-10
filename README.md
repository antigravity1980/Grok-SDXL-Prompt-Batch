# ComfyUI Grok SDXL Prompt Batch

Generate large batches of SDXL prompts via Grok 4.1 API.

## Installation
1. Copy to `custom_nodes/`
2. `pip install -r requirements.txt`
3. Restart ComfyUI

## Set API Key
Set `GROK_API_KEY` env variable or pass via `api_key` parameter.

## Parameters
- user_task: Instruction for generation
- count: Number of prompts (1-10000)
- model: grok-4.1
- temperature: 0.7
- chunk_size: 100
- lora_mode: off/auto/force
- lora_source_mode: comfy_models_folder/json_index
- strip_numbering: True
- deduplicate: True

## Outputs
- prompts_text: All prompts separated by blank line
- count_generated: Actual count
- debug_info: JSON debug info
