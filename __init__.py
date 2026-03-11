from .nodes import GrokSDXLPromptBatch, GrokSDXLPromptBatchIdentical, GrokBatchImageGallery, GrokImageSaverNoMetadata, GrokSDXLAspectRatio, GrokTextBatchSplitter
from .lora_loaders import GrokLoraLoaderAutoText, GrokLoraLoaderAI

NODE_CLASS_MAPPINGS = {
    "GrokSDXLPromptBatch": GrokSDXLPromptBatch,
    "GrokSDXLPromptBatchIdentical": GrokSDXLPromptBatchIdentical,
    "GrokLoraLoaderAutoText": GrokLoraLoaderAutoText,
    "GrokLoraLoaderAI": GrokLoraLoaderAI,
    "GrokBatchImageGallery": GrokBatchImageGallery,
    "GrokImageSaverNoMetadata": GrokImageSaverNoMetadata,
    "GrokSDXLAspectRatio": GrokSDXLAspectRatio,
    "GrokTextBatchSplitter": GrokTextBatchSplitter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokSDXLPromptBatch": "Grok SDXL Prompt Batch (Diverse)",
    "GrokSDXLPromptBatchIdentical": "Grok SDXL Prompt Batch (Identical)",
    "GrokLoraLoaderAutoText": "Grok Lora Loader (Auto-Text)",
    "GrokLoraLoaderAI": "Grok Lora Loader (AI Strategy)",
    "GrokBatchImageGallery": "Grok Batch Image Gallery",
    "GrokImageSaverNoMetadata": "Grok Image Saver",
    "GrokSDXLAspectRatio": "Grok SDXL Aspect Ratio",
    "GrokTextBatchSplitter": "Grok Text Batch Splitter",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
