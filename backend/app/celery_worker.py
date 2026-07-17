# import os
# import logging
# import time
# import random
# from typing import List
# from celery import Celery
# from pydantic import BaseModel, Field
# from datetime import datetime
# import shutil

# # Database and Core RAG Imports
# from app.core.config import settings, db, Shared_llm, Groq_llm, OpenRouter_llm
# from app.utils.audio_processor import process_input, process_local_input, upload_file_to_s3
# from app.core.transcriber import transcribe_all
# from app.core.vector_store import build_vector_store

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# tasks_col = db[settings.TASKS_COLLECTION]
# analyses_col = db["analyses"]

# REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# celery_app = Celery(
#     "video_tasks",
#     broker=REDIS_URL,
#     backend=REDIS_URL
# )

# celery_app.conf.update(
#     task_serializer='json',
#     accept_content=['json'],
#     result_serializer='json',
#     timezone='UTC',
#     enable_utc=True,
#     worker_prefetch_multiplier=1,
#     task_acks_late=True
# )

# class VideoAnalysisSchema(BaseModel):
#     title: str = Field(description="A concise catchy title for the video presentation.")
#     summary: str = Field(description="A high-level comprehensive bullet-pointed outline paragraph summary.")
#     action_items: List[str] = Field(description="A list of action items, technical assignments, or tasks.")
#     key_decisions: List[str] = Field(description="A list of core architectures, frameworks chosen, or agreements resolved.")
#     open_questions: List[str] = Field(description="A list of unresolved questions, confusing definitions, or follow-ups.")


# def execute_safe_single_pass(transcript_str: str) -> VideoAnalysisSchema:
#     prompt = f"""
#     Analyze this video transcript and extract all metadata requirements cleanly.
#     You MUST return your response as a valid JSON object matching this schema:
#     {{
#         "title": "Concise presentation title",
#         "summary": "High-level outline summary paragraph",
#         "action_items": ["item 1", "item 2"],
#         "key_decisions": ["decision 1", "decision 2"],
#         "open_questions": ["question 1"]
#     }}
    
#     Transcript:
#     {transcript_str}
#     """
    
#     try:
#         if hasattr(OpenRouter_llm, "max_tokens"):
#             OpenRouter_llm.max_tokens = 2000
#         elif hasattr(OpenRouter_llm, "model_kwargs"):
#             OpenRouter_llm.model_kwargs["max_tokens"] = 2000
#     except Exception:
#         pass

#     models_pool = [
#         {"name": "Primary (Mistral AI)", "engine": Shared_llm, "structured": True},
#         {"name": "Fallback 1 (Groq Llama 3.3)", "engine": Groq_llm, "structured": False}, 
#         {"name": "Fallback 2 (OpenRouter Gemini)", "engine": OpenRouter_llm, "structured": True}
#     ]
    
#     last_error = None
#     for model_node in models_pool:
#         model_name = model_node["name"]
#         llm_instance = model_node["engine"]
#         is_structured_supported = model_node["structured"]
        
#         max_retries = 2
#         for attempt in range(max_retries):
#             try:
#                 logger.info(f"⚡ Attempting structured extraction via provider: {model_name} (Attempt {attempt + 1})")
#                 if is_structured_supported:
#                     structured_llm = llm_instance.with_structured_output(VideoAnalysisSchema)
#                     result = structured_llm.invoke(prompt)
#                     if result and getattr(result, "title", None):
#                         return result
#                 else:
#                     import json
#                     import re
#                     response = llm_instance.invoke(prompt)
#                     raw_text = response.content if hasattr(response, 'content') else str(response)
                    
#                     json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
#                     if json_match:
#                         parsed_data = json.loads(json_match.group(0))
#                         return VideoAnalysisSchema(
#                             title=parsed_data.get("title", "Video Analysis Update"),
#                             summary=parsed_data.get("summary", "Summary processed via fallback engine."),
#                             action_items=parsed_data.get("action_items", []),
#                             key_decisions=parsed_data.get("key_decisions", []),
#                             open_questions=parsed_data.get("open_questions", [])
#                         )
#                 raise ValueError("Structured model response processed as empty target payload or parsing failure.")
#             except Exception as e:
#                 last_error = str(e)
#                 logger.warning(f"⚠️ Provider framework failure: {model_name} -> Error: {last_error}")
#                 if attempt < max_retries - 1:
#                     time.sleep(2)
        
#     raise RuntimeError(f"All available backup language generation units failed. Last error: {last_error}")


# @celery_app.task(name="app.celery_worker.process_remote_video_task")
# def process_remote_video_task(task_id: str, user_id: str, source_url: str, language: str):
#     chunks_created = []
#     try:
#         chunks_created = process_input(source_url)
#         timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
#         if not timestamped_segments:
#             raise ValueError("No transcript segments generated.")

#         master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
#         build_vector_store(timestamped_segments, task_id=task_id)

#         logger.info(f"🤖 Running Forced Single-Pass Unified Extraction Profile for Task: {task_id}")
#         analysis_result = execute_safe_single_pass(master_transcript_str)
            
#         title = analysis_result.title.strip()
#         summary = analysis_result.summary.strip()
#         action_items_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.action_items if str(item).strip()])
#         key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.key_decisions if str(item).strip()])
#         open_questions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.open_questions if str(item).strip()])

#         analyses_col.insert_one({
#             "_id": task_id,
#             "user_id": user_id,
#             "video_url": source_url,
#             "title": title,
#             "summary": summary,
#             "action_items": action_items_str.strip(),
#             "key_decisions": key_decisions_str.strip(),
#             "open_questions": open_questions_str.strip(),
#             "created_at": datetime.utcnow()
#         })
        
#         tasks_col.update_one({"_id": task_id}, {"$set": {"status": "completed"}})
#         logger.info(f"✅ Remote video ingestion pipeline completed successfully for task: {task_id}")
        
#     except Exception as e:
#         logger.error(f"Unified Ingestion Task failure -> {str(e)}")
#         tasks_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
#     finally:
#         for chunk_file in chunks_created:
#             if os.path.exists(chunk_file):
#                 os.remove(chunk_file)


# @celery_app.task(name="app.celery_worker.process_local_video_task")
# def process_local_video_task(task_id: str, user_id: str, temporary_video_path: str, language: str):
#     chunks_created = []
#     clean_video_filename = os.path.basename(temporary_video_path)
#     try:
#         # 1. Gather local temporary chunk layers
#         chunks_created = process_local_input(temporary_video_path)
        
#         # 2. Run Whisper transcription safely while segments are physical files
#         logger.info("🎤 Executing Whisper structural audio segmentation parsing loop...")
#         timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
#         if not timestamped_segments:
#             raise ValueError("No transcript segments generated from local media track.")

#         master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
        
#         # 3. Offload chunks to AWS S3 storage and free disk spaces immediately
#         s3_backed_keys = []
#         for local_chunk in chunks_created:
#             if os.path.exists(local_chunk):
#                 filename = os.path.basename(local_chunk)
#                 s3_key = f"chunks/{filename}"
                
#                 logger.info(f"📤 Migrating local partition to cloud asset layer: {s3_key}...")
#                 upload_file_to_s3(local_chunk, s3_key)
#                 s3_backed_keys.append(s3_key)
                
#                 os.remove(local_chunk)
#                 logger.info(f"🗑️ Cleaned temporary storage volume block for: {filename}")

#         # 4. Ingest parsed metrics directly to RAG Vector Store DB
#         build_vector_store(timestamped_segments, task_id=task_id)

#         logger.info(f"🤖 Running Forced Single-Pass Unified Extraction Profile for Local Task: {task_id}")
#         analysis_result = execute_safe_single_pass(master_transcript_str)
            
#         title = analysis_result.title.strip() if analysis_result.title else clean_video_filename
#         summary = analysis_result.summary.strip() if analysis_result.summary else "Summary generation empty."
#         action_items_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.action_items if str(item).strip()])
#         key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.key_decisions if str(item).strip()])
#         open_questions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.open_questions if str(item).strip()])

#         analyses_col.insert_one({
#             "_id": task_id,
#             "user_id": user_id,
#             "video_url": "Local Uploaded File",
#             "title": title,
#             "summary": summary,
#             "action_items": action_items_str.strip(),
#             "key_decisions": key_decisions_str.strip(),
#             "open_questions": open_questions_str.strip(),
#             "s3_keys": s3_backed_keys, 
#             "created_at": datetime.utcnow()
#         })
        
#         tasks_col.update_one({"_id": task_id}, {"$set": {"status": "completed"}})
#         logger.info(f"✅ Local video ingestion pipeline completed successfully for task: {task_id}")
        
#     except Exception as e:
#         logger.error(f"Local video pipeline task failure -> {str(e)}")
#         tasks_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
#     finally:
#         if os.path.exists(temporary_video_path):
#             os.remove(temporary_video_path)
#         for chunk_file in chunks_created:
#             if os.path.exists(chunk_file):
#                 os.remove(chunk_file)

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
from app.utils.audio_processor import process_input, process_local_input, upload_file_to_s3
from app.core.transcriber import transcribe_all
from app.core.vector_store import build_vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tasks_col = db[settings.TASKS_COLLECTION]
analyses_col = db["analyses"]

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "video_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True
)

class VideoAnalysisSchema(BaseModel):
    title: str = Field(description="A concise catchy title for the video presentation.")
    summary: str = Field(description="A high-level comprehensive bullet-pointed outline paragraph summary.")
    action_items: List[str] = Field(description="A list of action items, technical assignments, or tasks.")
    key_decisions: List[str] = Field(description="A list of core architectures, frameworks chosen, or agreements resolved.")
    open_questions: List[str] = Field(description="A list of unresolved questions, confusing definitions, or follow-ups.")


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
    
    try:
        if hasattr(OpenRouter_llm, "max_tokens"):
            OpenRouter_llm.max_tokens = 2000
        elif hasattr(OpenRouter_llm, "model_kwargs"):
            OpenRouter_llm.model_kwargs["max_tokens"] = 2000
    except Exception:
        pass

    models_pool = [
        {"name": "Primary (Mistral AI)", "engine": Shared_llm, "structured": True},
        {"name": "Fallback 1 (Groq Llama 3.3)", "engine": Groq_llm, "structured": False}, 
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
                    import json
                    import re
                    response = llm_instance.invoke(prompt)
                    raw_text = response.content if hasattr(response, 'content') else str(response)
                    
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


@celery_app.task(name="app.celery_worker.process_remote_video_task")
def process_remote_video_task(task_id: str, user_id: str, source_url: str, language: str):
    chunks_created = []
    try:
        chunks_created = process_input(source_url)
        timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
        if not timestamped_segments:
            raise ValueError("No transcript segments generated.")

        master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
        
        # 🪙 LLM Cost Boundaries & Token Limit Guardrail Check
        estimated_tokens = len(master_transcript_str) // 4
        logger.info(f"📊 Task {task_id} generated transcription length metrics: ~{estimated_tokens} tokens.")
        if estimated_tokens > settings.MAX_TRANSCRIPT_TOKENS:
            raise ValueError(f"Cost Guardrail Triggered: Transcript context size (~{estimated_tokens} tokens) exceeds allowance ceiling of {settings.MAX_TRANSCRIPT_TOKENS} tokens.")

        build_vector_store(timestamped_segments, task_id=task_id)

        logger.info(f"🤖 Running Forced Single-Pass Unified Extraction Profile for Task: {task_id}")
        analysis_result = execute_safe_single_pass(master_transcript_str)
            
        title = analysis_result.title.strip()
        summary = analysis_result.summary.strip()
        action_items_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.action_items if str(item).strip()])
        key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.key_decisions if str(item).strip()])
        open_questions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.open_questions if str(item).strip()])

        analyses_col.insert_one({
            "_id": task_id,
            "user_id": user_id,
            "video_url": source_url,
            "title": title,
            "summary": summary,
            "action_items": action_items_str.strip(),
            "key_decisions": key_decisions_str.strip(),
            "open_questions": open_questions_str.strip(),
            "created_at": datetime.utcnow()
        })
        
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "completed"}})
        logger.info(f"✅ Remote video ingestion pipeline completed successfully for task: {task_id}")
        
    except Exception as e:
        logger.error(f"Unified Ingestion Task failure -> {str(e)}")
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
    finally:
        for chunk_file in chunks_created:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)


@celery_app.task(name="app.celery_worker.process_local_video_task")
def process_local_video_task(task_id: str, user_id: str, temporary_video_path: str, language: str):
    chunks_created = []
    clean_video_filename = os.path.basename(temporary_video_path)
    try:
        # 1. Gather local temporary chunk layers
        chunks_created = process_local_input(temporary_video_path)
        
        # 2. Run Whisper transcription safely while segments are physical files
        logger.info("🎤 Executing Whisper structural audio segmentation parsing loop...")
        timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
        if not timestamped_segments:
            raise ValueError("No transcript segments generated from local media track.")

        master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
        
        # 🪙 LLM Cost Boundaries & Token Limit Guardrail Check
        estimated_tokens = len(master_transcript_str) // 4
        logger.info(f"📊 Task {task_id} generated transcription length metrics: ~{estimated_tokens} tokens.")
        if estimated_tokens > settings.MAX_TRANSCRIPT_TOKENS:
            raise ValueError(f"Cost Guardrail Triggered: Local transcript context size (~{estimated_tokens} tokens) exceeds allowance ceiling of {settings.MAX_TRANSCRIPT_TOKENS} tokens.")

        # 3. Offload chunks to AWS S3 storage and free disk spaces immediately
        s3_backed_keys = []
        for local_chunk in chunks_created:
            if os.path.exists(local_chunk):
                filename = os.path.basename(local_chunk)
                s3_key = f"chunks/{filename}"
                
                logger.info(f"📤 Migrating local partition to cloud asset layer: {s3_key}...")
                upload_file_to_s3(local_chunk, s3_key)
                s3_backed_keys.append(s3_key)
                
                os.remove(local_chunk)
                logger.info(f"🗑️ Cleaned temporary storage volume block for: {filename}")

        # 4. Ingest parsed metrics directly to RAG Vector Store DB
        build_vector_store(timestamped_segments, task_id=task_id)

        logger.info(f"🤖 Running Forced Single-Pass Unified Extraction Profile for Local Task: {task_id}")
        analysis_result = execute_safe_single_pass(master_transcript_str)
            
        title = analysis_result.title.strip() if analysis_result.title else clean_video_filename
        summary = analysis_result.summary.strip() if analysis_result.summary else "Summary generation empty."
        action_items_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.action_items if str(item).strip()])
        key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.key_decisions if str(item).strip()])
        open_questions_str = "\n".join([f"- {str(item).strip()}" for item in analysis_result.open_questions if str(item).strip()])

        analyses_col.insert_one({
            "_id": task_id,
            "user_id": user_id,
            "video_url": "Local Uploaded File",
            "title": title,
            "summary": summary,
            "action_items": action_items_str.strip(),
            "key_decisions": key_decisions_str.strip(),
            "open_questions": open_questions_str.strip(),
            "s3_keys": s3_backed_keys, 
            "created_at": datetime.utcnow()
        })
        
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "completed"}})
        logger.info(f"✅ Local video ingestion pipeline completed successfully for task: {task_id}")
        
    except Exception as e:
        logger.error(f"Local video pipeline task failure -> {str(e)}")
        tasks_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": str(e)}})
    finally:
        if os.path.exists(temporary_video_path):
            os.remove(temporary_video_path)
        for chunk_file in chunks_created:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)