import os
import json
import folder_paths
import comfy.sd
import comfy.utils

class GrokLoraLoaderBase:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {}}
        
    def _parse_strength_overrides(self, override_text):
        overrides = {}
        if not override_text:
            return overrides
            
        lines = override_text.split('\n')
        for line in lines:
            if ':' in line:
                parts = line.split(':', 1)
                name = parts[0].strip()
                try:
                    val = float(parts[1].strip())
                    overrides[name] = val
                    # Also strip .safetensors for easier matching
                    if name.endswith('.safetensors'):
                        overrides[name[:-12]] = val
                except ValueError:
                    pass
        return overrides

    def _load_loras(self, model, clip, loras_to_load):
        debug_lines = []
        for lreq in loras_to_load:
            name = lreq["name"]
            st = lreq["strength"]
            
            if st == 0:
                debug_lines.append(f"⏭ Skipped: {name} (Strength is 0)")
                continue
                
            lora_path = folder_paths.get_full_path("loras", name)
            if not lora_path:
                debug_lines.append(f"❌ ERROR: LoRA '{name}' not found on disk.")
                continue
                
            try:
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                model, clip = comfy.sd.load_lora_for_models(model, clip, lora, st, st)
                debug_lines.append(f"✅ Loaded: {name} (Strength: {st:.2f})")
            except Exception as e:
                debug_lines.append(f"❌ ERROR loading {name}: {str(e)}")
                
        return model, clip, "\n".join(debug_lines)


class GrokLoraLoaderAutoText(GrokLoraLoaderBase):
    """Variant A: Reads Grok's used_loras, applies a default strength, allows text override."""
    CATEGORY = "Grok/LoRA Loaders"
    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "loader_debug_text")
    FUNCTION = "load_loras"

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "used_loras": ("STRING", {"forceInput": True}),
                "default_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.1}),
                "lora_strengths": ("STRING", {"multiline": True, "dynamicPrompts": True, "default": "# Example:\n# Tape_people.safetensors: 1.2"}),
            }
        }

    def load_loras(self, model, clip, used_loras, default_strength, lora_strengths):
        overrides = self._parse_strength_overrides(lora_strengths)
        
        try:
            lora_data = json.loads(used_loras)
        except:
            lora_data = []

        loras_to_load = []
        for l in lora_data:
            name = l.get("name")
            if not name: continue
            
            # Check for override (with and without extension)
            st = default_strength
            base_name = name[:-12] if name.endswith('.safetensors') else name
            
            if name in overrides:
                st = overrides[name]
            elif base_name in overrides:
                st = overrides[base_name]
                
            loras_to_load.append({"name": name, "strength": st})

        model, clip, debug_txt = self._load_loras(model, clip, loras_to_load)
            
        if not loras_to_load:
            debug_txt = "ℹ️ No LoRAs were requested by Grok."

        return (model, clip, debug_txt)


class GrokLoraLoaderAI(GrokLoraLoaderBase):
    """Variant B: Reads loras_with_ai_strength, applies it, allows text override."""
    CATEGORY = "Grok/LoRA Loaders"
    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "loader_debug_text")
    FUNCTION = "load_loras"

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "loras_with_ai_strength": ("STRING", {"forceInput": True}),
                "strength_override": ("STRING", {"multiline": True, "dynamicPrompts": True, "default": "# Override AI's choice here:\n# princess_xl_v2.safetensors: 0.8"}),
            }
        }

    def load_loras(self, model, clip, loras_with_ai_strength, strength_override):
        overrides = self._parse_strength_overrides(strength_override)
        
        try:
            lora_data = json.loads(loras_with_ai_strength)
        except:
            lora_data = []

        loras_to_load = []
        for l in lora_data:
            name = l.get("name")
            if not name: continue
            
            # AI assigned strength, default to 1.0 if not present
            st = l.get("strength", 1.0)
            
            # Manual override overrides AI
            base_name = name[:-12] if name.endswith('.safetensors') else name
            if name in overrides:
                st = overrides[name]
            elif base_name in overrides:
                st = overrides[base_name]
                
            loras_to_load.append({"name": name, "strength": st})

        model, clip, debug_txt = self._load_loras(model, clip, loras_to_load)
            
        if not loras_to_load:
            debug_txt = "ℹ️ No LoRAs were requested by Grok."

        return (model, clip, debug_txt)
