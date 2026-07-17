import os
import logging
import time
import random
from typing import List
from celery import Celery
from pydantic import BaseModel, Field
from datetime import datetime
import shutil

# Database and Core RAG Imports
from app.core.config import settings, db, Shared_llm, Groq_llm, OpenRouter_llm
from app.utils.audio_processor import process_input, process_local_input
from app.core.transcriber import transcribe_all
from app.core.vector_store import build_vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Re-read MongoDB collections mappings
tasks_col = db[settings.TASKS_COLLECTION]
analyses_col = db["analyses"]

# Fetch local Redis URL from environment variables, falling back gracefully to standard localhost
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery app context targeting Redis as the broker and backend storage
celery_app = Celery(
    "video_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Optimize Celery worker allocations for a low-resource EC2 instance tier
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1, # 👈 Don't hoard tasks; process them one-by-one to save memory
    task_acks_late=True           # 👈 If the container crashes, return the job back to the queue safely!
)

class VideoAnalysisSchema(BaseModel):
    title: str = Field(description="A concise catchy title for the video presentation.")
    summary: str = Field(description="A high-level comprehensive bullet-pointed outline paragraph summary.")
    action_items: List[str] = Field(description="A list of action items, technical assignments, or tasks.")
    key_decisions: List[str] = Field(description="A list of core architectures, frameworks chosen, or agreements resolved.")
    open_questions: List[str] = Field(description="A list of unresolved questions, confusing definitions, or follow-ups.")

# Inside app/celery_worker.py

def execute_safe_single_pass(transcript_str: str) -> VideoAnalysisSchema:
    prompt = f"""
    Analyze this video transcript and extract all metadata requirements cleanly.
    You MUST return your response as a valid JSON object matching this schema:
    {{
        "title": "Concise presentation title",
        "summary": "High-level outline summary paragraph",
        "action_items": ["item 1", "item 2"],
        "key_decisions": ["decision 1", "decision 2"],
        "open_questions": ["question 1"]
    }}
    
    Transcript:
    {transcript_str}
    """
    
    # Configure safety constraints directly on your fallback instances
    try:
        # Prevent OpenRouter from requesting max context windows that trip a 402 error
        if hasattr(OpenRouter_llm, "max_tokens"):
            OpenRouter_llm.max_tokens = 2000
        elif hasattr(OpenRouter_llm, "model_kwargs"):
            OpenRouter_llm.model_kwargs["max_tokens"] = 2000
    except Exception:
        pass

    models_pool = [
        {"name": "Primary (Mistral AI)", "engine": Shared_llm, "structured": True},
        {"name": "Fallback 1 (Groq Llama 3.3)", "engine": Groq_llm, "structured": False}, # Use robust manual parsing if fallback structural engine drops out
        {"name": "Fallback 2 (OpenRouter Gemini)", "engine": OpenRouter_llm, "structured": True}
    ]
    
    last_error = None
    
    for model_node in models_pool:
        model_name = model_node["name"]
        llm_instance = model_node["engine"]
        is_structured_supported = model_node["structured"]
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"⚡ Attempting structured extraction via provider: {model_name} (Attempt {attempt + 1})")
                
                if is_structured_supported:
                    structured_llm = llm_instance.with_structured_output(VideoAnalysisSchema)
                    result = structured_llm.invoke(prompt)
                    if result and getattr(result, "title", None):
                        return result
                else:
                    # Robust fallback parsing strategy for Groq/Llama
                    import json
                    import re
                    response = llm_instance.invoke(prompt)
                    raw_text = response.content if hasattr(response, 'content') else str(response)
                    
                    # Regex extract to isolate structural JSON content cleanly out of markdown blocks
                    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    if json_match:
                        parsed_data = json.loads(json_match.group(0))
                        return VideoAnalysisSchema(
                            title=parsed_data.get("title", "Video Analysis Update"),
                            summary=parsed_data.get("summary", "Summary processed via fallback engine."),
                            action_items=parsed_data.get("action_items", []),
                            key_decisions=parsed_data.get("key_decisions", []),
                            open_questions=parsed_data.get("open_questions", [])
                        )
                
                raise ValueError("Structured model response processed as empty target payload or parsing failure.")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ Provider framework failure: {model_name} -> Error: {last_error}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
    raise RuntimeError(f"All available backup language generation units failed. Last error: {last_error}")