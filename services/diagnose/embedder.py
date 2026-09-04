try:
    import google.generativeai as genai
    from packages.config.settings import settings
    genai.configure(api_key=settings.gemini_api_key)
except (ImportError, OSError, Exception):
    genai = None

import structlog
import typing

def embed_text(text: str) -> typing.List[float]:
    """Generates a 768-dimensional embedding for the given text using Gemini."""
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        return result['embedding']
    except Exception as e:
        logger.error("embedding_generation_failed", error=str(e))
        # Return fallback zero-vector in case of total failure so we don't crash, 
        # though this will just miss the cache anyway.
        return [0.0] * 768
