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

def execute_safe_single_pass(transcript_str: str) -> VideoAnalysisSchema:
    prompt = f"Analyze this video transcript and extract all metadata requirements cleanly:\n{transcript_str}"
    models_pool = [
        {"name": "Primary (Mistral AI)", "engine": Shared_llm},
        {"name": "Fallback 1 (Groq Llama 3.3)", "engine": Groq_llm},
        {"name": "Fallback 2 (OpenRouter Gemini)", "engine": OpenRouter_llm}
    ]
    last_error = None
    
    for model_node in models_pool:
        model_name = model_node["name"]
        llm_instance = model_node["engine"]
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"⚡ Attempting structured extraction via provider: {model_name} (Attempt {attempt + 1})")
                structured_llm = llm_instance.with_structured_output(VideoAnalysisSchema)
                result = structured_llm.invoke(prompt)
                
                if result is not None and getattr(result, "title", None):
                    return result
                raise ValueError("Structured model response processed as empty target payload or NoneType.")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ Provider framework failure: {model_name} -> Error: {last_error}")
                if attempt < max_retries - 1:
                    time.sleep((2 ** attempt) + random.uniform(0, 1))
        
    raise RuntimeError(f"All available backup language generation units failed. Last error: {last_error}")

# --- ASYNC CELERY TASK WRAPPERS ---
@celery_app.task(name="celery_worker.process_remote_video_task")
def process_remote_video_task(task_id: str, user_id: str, source_url: str, language: str):
    chunks_created = []
    try:
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "processing"}})
        chunks_created = process_input(source_url)
        timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
        if not timestamped_segments:
            raise ValueError("No transcript segments generated.")

        master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
        build_vector_store(timestamped_segments, task_id=task_id)

        analysis_result = execute_safe_single_pass(master_transcript_str)
            
        action_items_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.action_items if str(item).strip()])
        key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.key_decisions if str(item).strip()])
        open_questions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.open_questions if str(item).strip()])

        analyses_col.insert_one({
            "_id": task_id,
            "user_id": user_id,
            "video_url": source_url,
            "title": analysis_result.title.strip(),
            "summary": analysis_result.summary.strip(),
            "action_items": action_items_str.strip(),
            "key_decisions": key_decisions_str.strip(),
            "open_questions": open_questions_str.strip(),
            "created_at": datetime.utcnow()
        })
        
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "completed"}})
        logger.info(f"✅ Celery remote video ingestion task completed successfully: {task_id}")
    except Exception as e:
        logger.error(f"❌ Celery Remote Task failure -> {str(e)}")
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
    finally:
        for chunk_file in chunks_created:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)

@celery_app.task(name="celery_worker.process_local_video_task")
def process_local_video_task(task_id: str, user_id: str, temporary_video_path: str, language: str):
    chunks_created = []
    clean_video_filename = os.path.basename(temporary_video_path)
    try:
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "processing"}})
        chunks_created = process_local_input(temporary_video_path)
        timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
        if not timestamped_segments:
            raise ValueError("No transcript segments generated from local media track.")

        master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
        build_vector_store(timestamped_segments, task_id=task_id)

        analysis_result = execute_safe_single_pass(master_transcript_str)
            
        title = analysis_result.title.strip() if analysis_result.title else clean_video_filename
        action_items_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.action_items if str(item).strip()])
        key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.key_decisions if str(item).strip()])
        open_questions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.open_questions if str(item).strip()])

        analyses_col.insert_one({
            "_id": task_id,
            "user_id": user_id,
            "video_url": "Local Uploaded File",
            "title": title,
            "summary": analysis_result.summary.strip(),
            "action_items": action_items_str.strip(),
            "key_decisions": key_decisions_str.strip(),
            "open_questions": open_questions_str.strip(),
            "created_at": datetime.utcnow()
        })
        
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "completed"}})
        logger.info(f"✅ Celery local video ingestion task completed successfully: {task_id}")
    except Exception as e:
        logger.error(f"❌ Celery Local Task failure -> {str(e)}")
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
    finally:
        if os.path.exists(temporary_video_path):
            os.remove(temporary_video_path)
        for chunk_file in chunks_created:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)