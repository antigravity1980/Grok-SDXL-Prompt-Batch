import os
import time
import requests
from typing import List, Optional, Dict, Any, Tuple

class GrokClient:
    DEFAULT_MODEL = "grok-4-1-fast-non-reasoning"
    DEFAULT_TEMPERATURE = 0.7
    MAX_RETRIES = 3
    BASE_BACKOFF = 2
    
    def __init__(self, api_key=None, model=None, temperature=None):
        self.api_key = api_key or os.environ.get("GROK_API_KEY")
        if not self.api_key:
            raise ValueError("Grok API key not provided")
        self.model = model or self.DEFAULT_MODEL
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        self.base_url = "https://api.x.ai/v1"
    
    def _get_headers(self):
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
    
    def _make_request(self, messages, max_tokens=4096):
        url = f"{self.base_url}/chat/completions"
        payload = {"model": self.model, "messages": messages, "temperature": self.temperature, "max_tokens": max_tokens}
        r = requests.post(url, headers=self._get_headers(), json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("choices", [{}])[0].get("message", {}).get("content")
    
    def generate_with_retry(self, system_prompt, user_prompt, max_tokens=4096):
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                result = self._make_request(messages, max_tokens)
                if result:
                    return result
            except requests.exceptions.HTTPError as e:
                last_exception = Exception(f"HTTP Error {e.response.status_code}: {e.response.text}")
                if e.response.status_code in (400, 401, 403, 404):
                    raise last_exception
            except Exception as e:
                last_exception = e
            time.sleep(self.BASE_BACKOFF * (2 ** attempt))
        raise RuntimeError(f"Grok API Failed after {self.MAX_RETRIES} attempts. Last error: {str(last_exception)}")
    
    def generate_chunked(self, system_prompt, user_instruction, total_count, chunk_size):
        all_prompts, debug = [], {"api_calls": 0, "chunks": [], "errors": []}
        remaining, idx = total_count, 0
        while remaining > 0:
            cur = min(remaining, chunk_size)
            instr = f"{user_instruction}\n\nGenerate exactly {cur} prompts separated by blank lines."
            resp = self.generate_with_retry(system_prompt, instr)
            debug["api_calls"] += 1
            if resp:
                prompts = self._parse(resp)
                all_prompts.extend(prompts)
                debug["chunks"].append({"chunk": idx + 1, "requested": cur, "got": len(prompts)})
            remaining -= cur
            idx += 1
        return all_prompts, debug
    
    def _parse(self, response):
        prompts, current = [], []
        for line in response.strip().split("\n"):
            if not line.strip():
                if current:
                    prompts.append(" ".join(current))
                    current = []
            else:
                current.append(line.strip())
        if current:
            prompts.append(" ".join(current))
        return prompts
