import os
import json
import glob
import struct
from typing import List, Dict, Any, Optional

class LoRAIndexer:
    def __init__(self):
        self.lora_list = []
        self.metadata_cache = {}
        self.cache_file = self._get_cache_path()
        self._load_cache()

    def _get_cache_path(self):
        # Store cache in the same folder as the node
        return os.path.join(os.path.dirname(__file__), "lora_metadata_cache.json")

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.metadata_cache = json.load(f)
            except Exception:
                self.metadata_cache = {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.metadata_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _read_safetensors_metadata(self, path):
        if path in self.metadata_cache:
            # Check if file modification time is the same
            mtime = os.path.getmtime(path)
            if self.metadata_cache[path].get("mtime") == mtime:
                return self.metadata_cache[path]

        try:
            with open(path, 'rb') as f:
                header_size_bytes = f.read(8)
                if len(header_size_bytes) < 8: return {}
                header_size = struct.unpack('<Q', header_size_bytes)[0]
                header_bytes = f.read(header_size)
                header = json.loads(header_bytes)
                metadata = header.get('__metadata__', {})
                
                # Extract trigger words from typical fields
                triggers = []
                # Common training word fields
                for key in ["ss_trained_words", "ss_tag_frequency"]:
                    val = metadata.get(key)
                    if isinstance(val, str):
                        try:
                            # Sometimes it's a JSON string of a list
                            parsed = json.loads(val)
                            if isinstance(parsed, list): triggers.extend(parsed)
                            elif isinstance(parsed, dict): triggers.extend(parsed.keys())
                        except:
                            # Otherwise treat as comma-separated
                            triggers.extend([t.strip() for t in val.split(",") if t.strip()])
                
                # Clean up triggers
                triggers = list(set([t for t in triggers if len(t) > 2]))
                
                result = {
                    "trigger_words": triggers[:15], # Limit to 15 triggers
                    "mtime": os.path.getmtime(path),
                    "ss_training_comment": metadata.get("ss_training_comment", "")
                }
                self.metadata_cache[path] = result
                return result
        except Exception:
            return {}

    def scan_comfyui_lora_folder(self, comfyui_path=None):
        lora_entries = []
        try:
            import folder_paths
            # Get actual names that ComfyUI uses (which include subdirectories like "architecture/building.safetensors")
            comfy_names = folder_paths.get_filename_list("loras")
            for name in comfy_names:
                full_path = folder_paths.get_full_path("loras", name)
                if full_path:
                    lora_entries.append({"name": name, "path": full_path})
        except ImportError:
            # Fallback for manual testing outside of ComfyUI
            paths = [os.path.join(os.path.expanduser("~"), "ComfyUI", "models", "loras"), "C:\\ComfyUI\\models\\loras"]
            if comfyui_path:
                paths.insert(0, os.path.join(comfyui_path, "models", "loras"))
                
            for p in paths:
                if os.path.isdir(p):
                    found = glob.glob(os.path.join(p, "**/*.safetensors"), recursive=True)
                    for f in found:
                        rel_name = os.path.relpath(f, p).replace("\\", "/")
                        lora_entries.append({"name": rel_name, "path": f})
        
        # Deduplicate by path
        seen_paths = set()
        unique_entries = []
        for e in lora_entries:
            if e["path"] not in seen_paths:
                seen_paths.add(e["path"])
                unique_entries.append(e)

        self.lora_list = []
        for entry in unique_entries:
            meta = self._read_safetensors_metadata(entry["path"])
            self.lora_list.append({
                "name": entry["name"], # Now includes subdirectory!
                "path": entry["path"],
                "purpose": meta.get("ss_training_comment", self._infer_purpose(entry["path"])),
                "trigger_words": meta.get("trigger_words") or self._infer_triggers(entry["path"]),
                "strength_hint": None,
                "source": "comfy_models_folder"
            })
        
        self._save_cache()
        return self.lora_list
    
    def load_from_json(self, json_path):
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"LoRA index not found: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.lora_list = [{"name": e.get("name", "unknown"), "path": e.get("path", ""), "purpose": e.get("purpose", ""), "trigger_words": e.get("trigger_words", []), "strength_hint": e.get("strength_hint"), "source": "json_index"} for e in data]
        return self.lora_list
    
    def _extract_keywords(self, text):
        import re
        # Use regex to find words (supports Unicode/Cyrillic)
        words = re.findall(r'\w+', text, re.UNICODE)
        
    def _extract_keywords(self, text):
        # Even more robust split for Cyrillic/English: split by anything that isn't a letter or digit
        import re
        words = re.split(r'[^a-zA-Zа-яА-ЯёЁ0-9]+', text)
        
        stop = {"the", "with", "for", "and", "сделай", "нужно", "хочу", "напиши", "возле", "стоит", "из"}
        
        keywords = []
        for w in words:
            w = w.lower().strip()
            if len(w) >= 3 and w not in stop:
                keywords.append(w)
        return list(set(keywords))

    def find_relevant_loras(self, user_task, limit=20):
        if not self.lora_list:
            return []
        
        keywords = self._extract_keywords(user_task)
        relevant = []
        
        # 1. First, find LoRAs with direct keyword matches (highest priority)
        matched_indices = set()
        for idx, lora in enumerate(self.lora_list):
            score = 0
            purpose = str(lora.get("purpose", "")).lower()
            name = str(lora.get("name", "")).lower()
            triggers = " ".join(lora.get("trigger_words", [])).lower()
            
            for kw in keywords:
                if kw in purpose: score += 5
                if kw in name: score += 3
                if kw in triggers: score += 2
                
            if score > 0:
                c = lora.copy()
                c["relevance_score"] = score
                relevant.append(c)
                matched_indices.add(idx)
        
        relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        # 2. If we haven't reached the limit, add OTHER LoRAs as "potential candidates"
        # This is crucial for Russian prompts where Grok needs to translate the intent
        if len(relevant) < limit:
            remaining_loras = [l for i, l in enumerate(self.lora_list) if i not in matched_indices]
            # Add them with 0 score, just to fill the catalog for Grok
            for lora in remaining_loras:
                if len(relevant) >= limit: break
                c = lora.copy()
                c["relevance_score"] = 0
                relevant.append(c)
                    
        return relevant[:limit]
    
    def _infer_purpose(self, fn):
        n = fn.lower()
        if "beach" in n: return "beach, ocean"
        if "portrait" in n: return "portrait photography"
        if "landscape" in n: return "landscape, nature"
        if "cinematic" in n: return "cinematic, film"
        if "anime" in n: return "anime, manga"
        return "general style/subject"
    
    def _infer_triggers(self, fn):
        base = os.path.splitext(fn)[0].replace("_", " ").replace("-", " ")
        triggers = [w.lower() for w in base.split() if len(w) >= 4 and w.isalpha()]
        return triggers[:3] if triggers else [base.lower().replace(" ", "_")]
    
    def get_lora_context(self, relevant_loras, mode="auto"):
        if not relevant_loras:
            return ""
            
        parts = ["### CATALOG OF AVAILABLE LoRAs:", ""]
        for lora in relevant_loras[:20]:
            name = lora['name']
            purpose = lora.get('purpose', 'General style/subject')
            triggers = ", ".join(lora.get('trigger_words', []))
            
            parts.append(f"LoRA: {name}")
            parts.append(f"  Description/Purpose: {purpose}")
            if triggers:
                parts.append(f"  REQUIRED Trigger Words: {triggers}")
            parts.append("")
            
        parts.append("### SELECTION INSTRUCTIONS:")
        parts.append("Grok, use your internal reasoning and semantic understanding of both Russian and English to select the most appropriate LoRAs from the catalog above. If a LoRA matches the theme, style, or subject of the user's request, include its 'REQUIRED Trigger Words' in the comma-separated SDXL prompt.")
        
        return "\n".join(parts)

    def get_scanned_loras_report(self):
        if not self.lora_list:
            return "No LoRAs found in the scanned directories."
            
        report = [f"Found {len(self.lora_list)} LoRAs:", ""]
        for lora in self.lora_list:
            report.append(f"📁 {lora['name']}")
            if lora.get('trigger_words'):
                report.append(f"   Triggers: {', '.join(lora['trigger_words'])}")
            else:
                report.append("   Triggers: (None found)")
            report.append(f"   Purpose: {lora.get('purpose', 'N/A')}")
            report.append("")
        return "\n".join(report)
