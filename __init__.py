from .nodes import GrokSDXLPromptBatch, GrokBatchImageGallery
from .lora_loaders import GrokLoraLoaderAutoText, GrokLoraLoaderAI

NODE_CLASS_MAPPINGS = {
    "GrokSDXLPromptBatch": GrokSDXLPromptBatch,
    "GrokLoraLoaderAutoText": GrokLoraLoaderAutoText,
    "GrokLoraLoaderAI": GrokLoraLoaderAI,
    "GrokBatchImageGallery": GrokBatchImageGallery,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokSDXLPromptBatch": "Grok SDXL Prompt Batch",
    "GrokLoraLoaderAutoText": "Grok Lora Loader (Auto-Text)",
    "GrokLoraLoaderAI": "Grok Lora Loader (AI Strategy)",
    "GrokBatchImageGallery": "Grok Batch Image Gallery",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
