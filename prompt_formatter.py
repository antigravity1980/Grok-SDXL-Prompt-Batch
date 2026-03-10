import re
from typing import List

class PromptFormatter:
    @staticmethod
    def strip_numbering(prompts):
        patterns = [r"^\d+\.\s*", r"^\d+\)\s*", r"^\(\d+\)\s*"]
        result = []
        for p in prompts:
            for pat in patterns:
                p = re.sub(pat, "", p)
            result.append(p.strip())
        return result
    
    @staticmethod
    def deduplicate(prompts, normalize=True):
        seen, result = set(), []
        for p in prompts:
            norm = p.lower().strip()
            if norm and norm not in seen:
                seen.add(norm)
                result.append(p.strip())
        return result
    
    @staticmethod
    def validate(prompts, min_len=10):
        return [p.strip() for p in prompts if len(p.strip()) >= min_len]
    
    @staticmethod
    def join(prompts, sep="\n\n"):
        return sep.join(p.strip() for p in prompts if p.strip())
    
    @staticmethod
    def ensure_triggers(prompts, trigger_words, min_per=1):
        if not trigger_words:
            return prompts
        result = []
        for p in prompts:
            pl = p.lower()
            found = [t for t in trigger_words if t.lower() in pl]
            if len(found) >= min_per:
                result.append(p)
            else:
                result.append(f"{p}, {trigger_words[0]}")
        return result
