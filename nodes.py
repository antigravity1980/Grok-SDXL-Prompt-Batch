import json
import os
import random
import folder_paths
from PIL import Image, ImageDraw, ImageFont
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
            return ("Error generating prompts.", 0, json.dumps(debug, ensure_ascii=False), ld, "[]", "[]") 
    
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
            "5. NO TEXT ALLOWED: Absolutely DO NOT include descriptions of text, writing, signs, logos, words, or letters in the images. Exclude all text elements to prevent gibberish artifacts.",
            "6. NO token spam. Keep descriptions precise.",
            "7. Output ONLY the prompts, no numbering, no explanations or introductory text.",
            "",
            "SUBJECT & ENVIRONMENT DIVERSITY (CRITICAL & MANDATORY):",
            "1. When generating batches with people, you absolutely MUST randomly cycle through physical traits, locations, camera angles, and poses.",
            "2. LOCATION/BACKGROUND: Randomly alternate the setting for each prompt (e.g., bustling city street, quiet cafe, lush forest, neon alley, modern office, space station, ancient ruins).",
            "3. SHOT TYPE & ANGLE: Randomly alternate between extreme close-up, portrait, cowboy shot, full body, low angle, high angle, Dutch angle, drone view, etc.",
            "4. POSE: Randomly alternate poses (e.g., sitting, running, looking over shoulder, jumping, leaning against wall, dynamic action).",
            "5. HAIR COLOR: Randomly alternate between blonde, redhead, brunette, black hair, silver hair, etc.",
            "6. ETHNICITY: Randomly alternate between Asian, European, Slavic, African, Hispanic, Middle Eastern, etc.",
            "7. BODY TYPE: Randomly alternate between skinny, athletic, curvy, muscular, overweight, petite, etc.",
            "8. AGE: Randomly assign ages between 18 and 60 years old.",
            "9. NO DUPLICATES: Every prompt in the batch MUST use a unique combination of location, shot type, pose, and physical traits.",
            "10. Explicitly write these diverse environmental details, camera instructions, and character traits into the tags for every single prompt you generate.",
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
            "5. NO TEXT ALLOWED: Absolutely DO NOT include descriptions of text, writing, signs, logos, words, or letters in the images. Exclude all text elements to prevent gibberish artifacts.",
            "6. NO token spam. Keep descriptions precise.",
            "7. Output ONLY the prompts, no numbering, no explanations or introductory text.",
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
                     "filename_prefix": ("STRING", {"default": "Grok_Saved"})},
                "optional": {
                    "watermark_text": ("STRING", {"default": "", "multiline": False})
                },
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
                }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "Grok/Image Saver"

    def save_images(self, images, filename_prefix="Grok_Saved", watermark_text="", prompt=None, extra_pnginfo=None):
        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0])
        results = list()
        
        # Security: Intentionally discarding 'prompt' and 'extra_pnginfo' parameters 
        # so they NEVER reach the PNG header writer.

        for (batch_number, image) in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            # --- WATERMARK LOGIC ---
            if watermark_text and watermark_text.strip():
                try:
                    draw = ImageDraw.Draw(img)
                    # Dynamic sizing: Font size is roughly 2% of the image width, min 16px
                    font_size = max(16, int(img.width * 0.02))
                    
                    try:
                        # Try to load a standard truetype font (works on most Windows systems)
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except IOError:
                        # Fallback to default if arial is missing
                        font = ImageFont.load_default()
                        
                    text = watermark_text.strip()
                    # Calculate text bounding box
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    # Position: Bottom Right with padding
                    padding = int(font_size * 0.8)
                    x = img.width - text_width - padding
                    y = img.height - text_height - padding
                    
                    # Draw a subtle back shadow/outline for readability on any background
                    shadow_color = (0, 0, 0, 180) # Semi-transparent black
                    shadow_offset = max(1, int(font_size * 0.05))
                    
                    # Thick outline (8 directions)
                    offsets = [
                        (-shadow_offset, -shadow_offset), (0, -shadow_offset), (shadow_offset, -shadow_offset),
                        (-shadow_offset, 0),                                   (shadow_offset, 0),
                        (-shadow_offset, shadow_offset),  (0, shadow_offset),  (shadow_offset, shadow_offset)
                    ]
                    for dx, dy in offsets:
                        draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)
                                
                    # Main text (White with slight transparency)
                    draw.text((x, y), text, font=font, fill=(255, 255, 255, 220))
                except Exception as e:
                    print(f"Grok Watermark Error: {str(e)}")
            # -----------------------
            
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

class GrokSDXLAspectRatio:
    CATEGORY = "Grok/Image Options"
    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "get_resolution"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "aspect_ratio": ([
                    "🔳 1:1 (1024 x 1024)",
                    "🖥️ 16:9 (1344 x 768) Widescreen",
                    "📱 9:16 (768 x 1344) Portrait",
                    "🖼️ 3:2 (1216 x 832) Landscape",
                    "📝 2:3 (832 x 1216) Vertical",
                    "🎦 21:9 (1536 x 640) Cinematic",
                    "📸 4:3 (1152 x 896) Standard Camera"
                ], {"default": "🔳 1:1 (1024 x 1024)"}),
            }
        }
        
    def get_resolution(self, aspect_ratio):
        resolutions = {
            "🔳 1:1 (1024 x 1024)": (1024, 1024),
            "🖥️ 16:9 (1344 x 768) Widescreen": (1344, 768),
            "📱 9:16 (768 x 1344) Portrait": (768, 1344),
            "🖼️ 3:2 (1216 x 832) Landscape": (1216, 832),
            "📝 2:3 (832 x 1216) Vertical": (832, 1216),
            "🎦 21:9 (1536 x 640) Cinematic": (1536, 640),
            "📸 4:3 (1152 x 896) Standard Camera": (1152, 896)
        }
        # Default to 1024x1024 if something goes wrong
        width, height = resolutions.get(aspect_ratio, (1024, 1024))
        return (width, height)

class GrokTextBatchSplitter:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text_list",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "split"
    CATEGORY = "Grok/Utils"

    def split(self, text):
        # Split by double newline (our standard delimiter)
        # Filter out empty strings
        prompts = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not prompts:
            prompts = [""] # Fallback
            
        return (prompts,)


class GrokZImageTurboPromptBatch(GrokSDXLPromptBatch):
    CATEGORY = "Grok/Prompt Generation"
    
    def _build_system_prompt(self, lora_mode, relevant, lora_indexer, seed_style):
        parts = [
            "You are an expert prompt engineer for the Z-Image Turbo model (based on Stable Diffusion).", 
            "Your task is to create highly effective prompts tailored specifically for Z-Image Turbo based on the user's request.", 
            "", 
            "CRITICAL Z-IMAGE TURBO SYNTAX REQUIREMENTS:", 
            "1. NO NEGATIVE PROMPTS USED: Z-Image pipelines do not use negative prompts. Therefore, you MUST include all exclusions and constraints directly in the positive prompt.",
            "2. AESTHETIC BOOSTERS (MANDATORY): Begin every prompt with powerful quality tags: '(masterpiece, best quality, ultra-detailed:1.2), 8k resolution, photorealistic, (highly detailed face, realistic skin texture, perfect anatomy:1.2)'.",
            "3. EXCLUSION TAGS (MANDATORY): End every prompt with this exact blocking string to prevent deformities: '(deformed, distorted, disfigured, poorly drawn, bad anatomy, wrong anatomy, extra limb, missing limb, floating limbs, mutated hands, extra fingers, text, watermark, logo:1.4)'.",
            "4. HANDS & MULTIPLE PEOPLE: If the prompt involves hands or multiple people, you MUST add these tags immediately after the main subject: '(5 fingers per hand, natural hands, correct number of limbs, distinct individuals, cohesive scene:1.2)'.",
            "5. Be specific and detailed. Describe the scene like a movie director. Do not use vague words like 'nice' or 'beautiful'.",
            "6. Structure: Aesthetic Boosters -> Main Subject + Action -> [Hands/Limbs Tags] -> Setting & Environment -> Lighting & Mood -> Style -> Exclusion Tags.",
            "7. NO token spam. Keep descriptions precise (80 to 200 words max).",
            "6. Output ONLY the prompts, no numbering, no explanations or introductory text.",
            "",
            "SUBJECT & ENVIRONMENT DIVERSITY (CRITICAL & MANDATORY):",
            "1. When generating batches with people, you absolutely MUST randomly cycle through physical traits, locations, camera angles, and poses.",
            "2. LOCATION/BACKGROUND: Randomly alternate the setting for each prompt.",
            "3. SHOT TYPE & ANGLE: Randomly alternate between extreme close-up, portrait, cowboy shot, full body, low angle, high angle.",
            "4. POSE: Randomly alternate poses (e.g., sitting, running, looking over shoulder).",
            "5. NO DUPLICATES: Every prompt in the batch MUST use a unique combination of location, shot type, pose, and physical traits.",
            "",
            "LORA RULES (MAXIMUM PRIORITY):",
            "1. Use the CATALOG below as the source of truth.",
            "2. You MUST append tracking tags at the very end of the prompt in this exact format: <lora:filename> or <lora:filename:weight>.",
            "3. Always include matching trigger words from the catalog naturally within the prompt.",
        ]
        
        if lora_mode != "off" and relevant:
            lora_context = lora_indexer.get_lora_context(relevant, lora_mode)
            parts.append("\n" + lora_context)
            
        if seed_style:
            parts.append("")
            parts.append("STYLE CONSISTENCY: Keep the overall style consistent across all prompts in this batch, but vary the specific scene details.")
            
        return "\n".join(parts)


class GrokZImageTurboPromptBatchIdentical(GrokSDXLPromptBatchIdentical):
    CATEGORY = "Grok/Prompt Generation"

    def _build_system_prompt(self, lora_mode, relevant, lora_indexer, seed_style):
        parts = [
            "You are an expert prompt engineer for the Z-Image Turbo model (based on Stable Diffusion).", 
            "Your task is to create highly effective prompts tailored specifically for Z-Image Turbo based on the user's request.", 
            "", 
            "CRITICAL Z-IMAGE TURBO SYNTAX REQUIREMENTS:", 
            "1. NO NEGATIVE PROMPTS USED: Z-Image pipelines do not use negative prompts. Therefore, you MUST include all exclusions and constraints directly in the positive prompt.",
            "2. AESTHETIC BOOSTERS (MANDATORY): Begin every prompt with powerful quality tags: '(masterpiece, best quality, ultra-detailed:1.2), 8k resolution, photorealistic, (highly detailed face, realistic skin texture, perfect anatomy:1.2)'.",
            "3. EXCLUSION TAGS (MANDATORY): End every prompt with this exact blocking string to prevent deformities: '(deformed, distorted, disfigured, poorly drawn, bad anatomy, wrong anatomy, extra limb, missing limb, floating limbs, mutated hands, extra fingers, text, watermark, logo:1.4)'.",
            "4. HANDS & MULTIPLE PEOPLE: If the prompt involves hands or multiple people, you MUST add these tags immediately after the main subject: '(5 fingers per hand, natural hands, correct number of limbs, distinct individuals, cohesive scene:1.2)'.",
            "5. Structure: Aesthetic Boosters -> Main Subject + Action -> [Hands/Limbs Tags] -> Setting & Environment -> Lighting & Mood -> Style -> Exclusion Tags.",
            "6. Output ONLY the prompts, no numbering, no explanations.",
            "",
            "SUBJECT UNIFORMITY (CRITICAL & MANDATORY):",
            "1. When generating batches, you absolutely MUST make all prompts almost completely IDENTICAL.",
            "2. Do NOT randomly vary hair color, ethnicity, body type, age, clothing, or background.",
            "3. Every single prompt in the batch should describe the exact same person and the exact same scene.",
            "4. You may make only infinitesimal microscopic changes (like swapping synonyms) so the strings aren't literal duplicates.",
            "",
            "LORA RULES (MAXIMUM PRIORITY):",
            "1. Use the CATALOG below as the source of truth.",
            "2. You MUST append tracking tags at the very end of the prompt in this exact format: <lora:filename> or <lora:filename:weight>.",
            "3. Always include matching trigger words from the catalog naturally within the prompt.",
        ]
        
        if lora_mode != "off" and relevant:
            lora_context = lora_indexer.get_lora_context(relevant, lora_mode)
            parts.append("\n" + lora_context)
            
        if seed_style:
            parts.append("")
            parts.append("STYLE CONSISTENCY: Keep the overall style consistent across all prompts in this batch.")
            
        return "\n".join(parts)



