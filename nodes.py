import json
import os
import random
import folder_paths
from PIL import Image
import numpy as np
import re
from typing import Any, Dict, List, Tuple

from .grok_client import GrokClient
from .lora_indexer import LoRAIndexer
from .prompt_formatter import PromptFormatter

class GrokSDXLPromptBatch:
    CATEGORY = "Grok/Prompt Generation"
    RETURN_TYPES = ("STRING", "INT", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompts_text", "count_generated", "debug_info", "lora_debug", "used_loras", "loras_with_ai_strength")
    FUNCTION = "generate_prompts"
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "user_task": ("STRING", {"multiline": True, "default": "Generate 100 prompts"}),
                "count": ("INT", {"default": 100, "min": 1, "max": 10000, "step": 1}),
                "model": ("STRING", {"default": "grok-4-1-fast-non-reasoning"}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.1}),
                "chunk_size": ("INT", {"default": 100, "min": 1, "max": 500, "step": 1}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
                "seed_style_consistency": ("BOOLEAN", {"default": False}),
                "lora_mode": (["off", "auto", "force"], {"default": "off"}),
                "lora_source_mode": (["comfy_models_folder", "json_index"], {"default": "comfy_models_folder"}),
                "lora_index_path": ("STRING", {"default": ""}),
                "strip_numbering": ("BOOLEAN", {"default": True}),
                "deduplicate": ("BOOLEAN", {"default": True}),
            },
        }
    
    def generate_prompts(self, user_task, count, model, temperature, chunk_size, api_key="", seed_style_consistency=False, lora_mode="off", lora_source_mode="comfy_models_folder", lora_index_path="", strip_numbering=True, deduplicate=True):
        debug = {"status": "started", "requested_count": count}
        try:
            grok = GrokClient(api_key=api_key or None, model=model, temperature=temperature)
            lora_indexer = LoRAIndexer()
            relevant = []
            if lora_mode != "off":
                try:
                    if lora_source_mode == "json_index":
                        if not lora_index_path:
                            raise ValueError("lora_index_path required")
                        lora_indexer.load_from_json(lora_index_path)
                    else:
                        lora_indexer.scan_comfyui_lora_folder()
                    relevant = lora_indexer.find_relevant_loras(user_task)
                except Exception as e:
                    debug["lora_error"] = str(e)
                    lora_mode = "off"
            system_prompt = self._build_system_prompt(lora_mode, relevant, lora_indexer, seed_style_consistency)
            raw_prompts, api_debug = grok.generate_chunked(system_prompt, user_task, count, chunk_size)
            debug.update({"api_calls": api_debug["api_calls"], "chunks": api_debug["chunks"]})
            processed = raw_prompts
            if strip_numbering:
                processed = PromptFormatter.strip_numbering(processed)
            if deduplicate:
                processed = PromptFormatter.deduplicate(processed)
            processed = PromptFormatter.validate(processed)
            if lora_mode == "force" and relevant:
                triggers = [t for lora in relevant for t in lora.get("trigger_words", [])]
                if triggers:
                    processed = PromptFormatter.ensure_triggers(processed, triggers)
            prompts_text = PromptFormatter.join(processed)
            
            # --- Ecosystem Bridge: Calculate used LoRAs ---
            # NEW LOGIC: We now look for explicit <lora:filename> tags added by the AI
            used_loras_list = []
            ai_strength_list = []
            
            if relevant:
                # We need to process each prompt individually to remove the tags
                final_processed_prompts = []
                
                for prompt in processed:
                    current_prompt = prompt
                    
                    # Search for our custom tracking tags: <lora:filename> or <lora:filename:1.2>
                    # Allowing optional spaces around the name and strength
                    tag_pattern = r'<lora:\s*([^>:]+?)\s*(?::\s*([0-9.]+)\s*)?>'
                    
                    # Find all matches in this specific prompt
                    matches = re.finditer(tag_pattern, current_prompt)
                    for match in matches:
                        lora_name = match.group(1).strip()
                        strength_str = match.group(2)
                        
                        strength = 1.0
                        if strength_str:
                            try:
                                strength = float(strength_str.strip())
                            except ValueError:
                                pass
                                
                        # Check if this lora isn't already in our global list for this batch
                        _already_in_list = False
                        for l in used_loras_list:
                            existing_name = l["name"].lower()
                            existing_base = existing_name[:-12] if existing_name.endswith('.safetensors') else existing_name
                            if existing_name == lora_name.lower() or existing_base == lora_name.lower() or os.path.basename(existing_name) == os.path.basename(lora_name.lower()):
                                _already_in_list = True
                                break
                                
                        if not _already_in_list:
                            import os
                            # Verify the parsed name actually matches something in our relevant catalog
                            lora_base = lora_name[:-12].lower() if lora_name.lower().endswith('.safetensors') else lora_name.lower()
                            lora_basename = os.path.basename(lora_name)
                            lora_basename_noext = lora_basename[:-12].lower() if lora_basename.lower().endswith('.safetensors') else lora_basename.lower()
                            
                            for catalog_lora in relevant:
                                cat_name = catalog_lora["name"]
                                cat_base = cat_name[:-12].lower() if cat_name.lower().endswith('.safetensors') else cat_name.lower()
                                
                                cat_basename = os.path.basename(cat_name)
                                cat_basename_noext = cat_basename[:-12].lower() if cat_basename.lower().endswith('.safetensors') else cat_basename.lower()
                                
                                # 1. Try full string match (including subdirectories)
                                if cat_base == lora_base or cat_base.startswith(lora_base) or lora_base.startswith(cat_base):
                                    used_loras_list.append({"name": catalog_lora["name"]})
                                    ai_strength_list.append({"name": catalog_lora["name"], "strength": strength})
                                    break
                                # 2. Try basename match (in case Grok omitted the subdirectory)
                                elif cat_basename_noext == lora_basename_noext or cat_basename_noext.startswith(lora_basename_noext) or lora_basename_noext.startswith(cat_basename_noext):
                                    used_loras_list.append({"name": catalog_lora["name"]})
                                    ai_strength_list.append({"name": catalog_lora["name"], "strength": strength})
                                    break
                                    
                    # Remove the tracking tags from the user-facing prompt text
                    clean_prompt = re.sub(tag_pattern, '', current_prompt).strip()
                    # Clean up any trailing commas that might have been left behind
                    clean_prompt = re.sub(r',\s*$', '', clean_prompt)
                    final_processed_prompts.append(clean_prompt)
                
                # Replace the original processed list with our clean one
                processed = final_processed_prompts
                prompts_text = PromptFormatter.join(processed)

            used_loras_json = json.dumps(used_loras_list)
            ai_strength_json = json.dumps(ai_strength_list)
            # ----------------------------------------------
            
            debug["status"] = "success"
            debug["final_count"] = len(processed)
            debug["used_loras"] = used_loras_list
            
            lora_debug = lora_indexer.get_scanned_loras_report()
            
            return (prompts_text, len(processed), json.dumps(debug, ensure_ascii=False), lora_debug, used_loras_json, ai_strength_json)
        except Exception as e:
            debug["status"] = "error"
            debug["errors"] = [str(e)]
            # Even on error, try to return lora_debug if possible
            try:
                ld = lora_indexer.get_scanned_loras_report() if 'lora_indexer' in locals() else "Indexer not initialized"
            except:
                ld = "Error getting LoRA report"
            raise RuntimeError(f"Grok Error: {str(e)}") from e
    
    def _build_system_prompt(self, lora_mode, relevant, lora_indexer, seed_style):
        parts = [
            "You are an expert prompt engineer for Stable Diffusion XL (SDXL).", 
            "Your task is to create highly effective prompts for SDXL based on the user's request.", 
            "", 
            "CRITICAL SDXL SYNTAX REQUIREMENTS:", 
            "1. DO NOT use natural language sentences (like 'A picture of a...').",
            "2. Use a comma-separated list of tags and keywords (e.g. '1girl, beautiful lighting, cinematic, ...').",
            "3. Emphasize important elements by enclosing them in parentheses with weights, e.g., (masterpiece:1.2), (detailed:1.3).",
            "4. Start with the main subject, follow with details, environment, lighting, and style.",
            "5. NO token spam. Keep descriptions precise.",
            "6. Output ONLY the prompts, no numbering, no explanations or introductory text.",
            "",
            "SUBJECT DIVERSITY (CRITICAL & MANDATORY):",
            "1. When generating batches with people, you absolutely MUST randomly cycle through physical traits.",
            "2. HAIR COLOR: Randomly alternate between blonde, redhead, brunette, black hair, silver hair, etc.",
            "3. ETHNICITY: Randomly alternate between Asian, European, Slavic, African, Hispanic, Middle Eastern, etc.",
            "4. BODY TYPE: Randomly alternate between skinny, athletic, perfect figure, curvy, overweight, muscular, petite, etc.",
            "5. AGE: Randomly assign ages between 18 and 60 years old.",
            "6. NO DUPLICATES: Never generate two prompts in a row with the exact same combination of hair, ethnicity, body type, and age.",
            "7. Explicitly write these traits into the tags for every single person you generate.",
            "",
            "LORA SELECTION RULES (MAXIMUM PRIORITY):",
            "1. Below is a CATALOG of available LoRAs. You MUST use it as the source of truth.",
            "2. SEMANTIC MAPPING: If the user's request mentions or implies a subject, style, or character that exists in the catalog, YOU MUST USE THAT LoRA.",
            "3. IGNORE USER TRIGGER NAMES: If the user provides their own trigger words, you MUST ignore their version and USE THE CATALOG TRIGGERS EXACTLY.",
            "4. OUTPUT FORMAT: Each prompt MUST be a comma-separated list of SDXL tags. Include the catalog trigger words naturally but literally within that list.",
            "5. NO EXCEPTIONS: If a LoRA concept is in the catalog and matches the user's intent, its trigger words MUST be present in the output.",
            "6. TRACKING TAGS (CRITICAL): For EVERY LoRA you decide to use from the catalog, you MUST append a tracking tag at the very end of the prompt in this exact format: <lora:filename> (for example: <lora:tape_people.safetensors>).",
            "7. TRACKING TAGS STRENGTH: If you feel a specific LoRA needs a different strength (e.g., 0.6 or 1.2), format the tracking tag like this: <lora:filename:0.6>.",
            "8. You must include these <lora:...> tracking tags even if the LoRA has no required trigger words.",
        ]
        
        # Add LoRA context as a catalog
        if lora_mode != "off" and relevant:
            lora_context = lora_indexer.get_lora_context(relevant, lora_mode)
            parts.append("\n" + lora_context)
            
        if seed_style:
            parts.append("")
            parts.append("STYLE CONSISTENCY: Keep the overall style consistent across all prompts in this batch, but vary the specific scene details.")
            
        return "\n".join(parts)

class GrokSDXLPromptBatchIdentical(GrokSDXLPromptBatch):
    CATEGORY = "Grok/Prompt Generation"
    RETURN_TYPES = ("STRING", "INT", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompts_text", "count_generated", "debug_info", "lora_debug", "used_loras", "loras_with_ai_strength")
    FUNCTION = "generate_prompts"
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        types = super().INPUT_TYPES()
        required = dict(types["required"])
        optional = dict(types["optional"])
        
        required["user_task"] = ("STRING", {"multiline": True, "default": "Generate 10 prompts of the EXACT SAME character"})
        optional["deduplicate"] = ("BOOLEAN", {"default": False})
        
        return {
            "required": required,
            "optional": optional
        }

    def _build_system_prompt(self, lora_mode, relevant, lora_indexer, seed_style):
        parts = [
            "You are an expert prompt engineer for Stable Diffusion XL (SDXL).", 
            "Your task is to create highly effective prompts for SDXL based on the user's request.", 
            "", 
            "CRITICAL SDXL SYNTAX REQUIREMENTS:", 
            "1. DO NOT use natural language sentences (like 'A picture of a...').",
            "2. Use a comma-separated list of tags and keywords (e.g. '1girl, beautiful lighting, cinematic, ...').",
            "3. Emphasize important elements by enclosing them in parentheses with weights, e.g., (masterpiece:1.2), (detailed:1.3).",
            "4. Start with the main subject, follow with details, environment, lighting, and style.",
            "5. NO token spam. Keep descriptions precise.",
            "6. Output ONLY the prompts, no numbering, no explanations or introductory text.",
            "",
            "SUBJECT UNIFORMITY (CRITICAL & MANDATORY):",
            "1. When generating batches, you absolutely MUST make all prompts almost completely IDENTICAL.",
            "2. Do NOT randomly vary hair color, ethnicity, body type, age, clothing, or background.",
            "3. Every single prompt in the batch should describe the exact same person and the exact same scene.",
            "4. Keep the core subject constraints entirely constant so the images generated look like the same person.",
            "5. You may make only infinitesimal microscopic changes (like swapping synonyms or changing tag order) so the text strings aren't 100% literal duplicates, but the semantic meaning MUST remain identical.",
            "",
            "LORA SELECTION RULES (MAXIMUM PRIORITY):",
            "1. Below is a CATALOG of available LoRAs. You MUST use it as the source of truth.",
            "2. SEMANTIC MAPPING: If the user's request mentions or implies a subject, style, or character that exists in the catalog, YOU MUST USE THAT LoRA.",
            "3. IGNORE USER TRIGGER NAMES: If the user provides their own trigger words, you MUST ignore their version and USE THE CATALOG TRIGGERS EXACTLY.",
            "4. OUTPUT FORMAT: Each prompt MUST be a comma-separated list of SDXL tags. Include the catalog trigger words naturally but literally within that list.",
            "5. NO EXCEPTIONS: If a LoRA concept is in the catalog and matches the user's intent, its trigger words MUST be present in the output.",
            "6. TRACKING TAGS (CRITICAL): For EVERY LoRA you decide to use from the catalog, you MUST append a tracking tag at the very end of the prompt in this exact format: <lora:filename> (for example: <lora:tape_people.safetensors>).",
            "7. TRACKING TAGS STRENGTH: If you feel a specific LoRA needs a different strength (e.g., 0.6 or 1.2), format the tracking tag like this: <lora:filename:0.6>.",
            "8. You must include these <lora:...> tracking tags even if the LoRA has no required trigger words.",
        ]
        
        if lora_mode != "off" and relevant:
            lora_context = lora_indexer.get_lora_context(relevant, lora_mode)
            parts.append("\n" + lora_context)
            
        if seed_style:
            parts.append("")
            parts.append("STYLE CONSISTENCY: Keep the overall style consistent across all prompts in this batch.")
            
        return "\n".join(parts)

class GrokBatchImageGallery:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
                    "images": ("IMAGE", ),
                    "history_limit": ("INT", {"default": 100, "min": 1, "max": 1000, "step": 1}),
                },
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "Grok/Prompt Generation"
    SEARCH_ALIASES = ["grok", "gallery", "batch image gallery", "image viewer"]

    def __init__(self):
        self.output_dir = folder_paths.get_temp_directory()
        self.type = "temp"

    def save_images(self, images, history_limit, prompt=None, extra_pnginfo=None):
        results = list()
        for batch_number, image in enumerate(images):
            # ComfyUI image format is usually (B, H, W, C) where C is RGB and range is 0-1.
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            # Simple randomness to avoid caching issues on the frontend
            filename = f"grok_gallery_{random.randint(100000, 999999)}_{batch_number}.png"
            full_path = os.path.join(self.output_dir, filename)
            
            # Save compressed for fast previewing
            img.save(full_path, compress_level=4)
            
            results.append({
                "filename": filename,
                "subfolder": "",
                "type": self.type
            })

        return { "ui": { "grok_images": results } }

class GrokImageSaverNoMetadata:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = ""
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(s):
        return {"required": 
                    {"images": ("IMAGE", ),
                     "filename_prefix": ("STRING", {"default": "Grok_NoMeta"})},
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
                }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "Grok/Image Saver"

    def save_images(self, images, filename_prefix="Grok_NoMeta", prompt=None, extra_pnginfo=None):
        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0])
        results = list()
        
        # Security: Intentionally discarding 'prompt' and 'extra_pnginfo' parameters 
        # so they NEVER reach the PNG header writer.

        for (batch_number, image) in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            file = f"{filename}_{counter:05}_.png"
            full_path = os.path.join(full_output_folder, file)
            
            # Save strictly without the 'pnginfo' parameter.
            img.save(full_path, compress_level=self.compress_level)
            
            results.append({
                "filename": file,
                "subfolder": subfolder,
                "type": self.type
            })
            counter += 1

        return { "ui": { "images": results } }
