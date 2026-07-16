# import os
# import uuid
# import logging
# import time
# import random
# from typing import Dict, Any, List
# from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Depends, UploadFile, File
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.concurrency import run_in_threadpool
# from pydantic import BaseModel, EmailStr, Field
# from datetime import datetime
# import shutil

# # Core RAG/Extraction Imports
# from app.utils.audio_processor import process_local_input
# from app.core.transcriber import transcribe_all
# from app.core.summarize import rate_limit_safe_llm
# from app.core.vector_store import build_vector_store
# from app.core.rag_engine import load_rag_chain, ask_question
# from app.core.config import settings, db, Shared_llm,Groq_llm, OpenRouter_llm

# # MongoDB Auth Collections & Helpers
# from app.core.auth import get_current_user, hash_password, verify_password, create_access_token, users_col, analyses_col, chats_col

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# app = FastAPI(title="AI Video Assistant Authenticated API")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.ALLOWED_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# tasks_col = db[settings.TASKS_COLLECTION]

# # --- SCHEMAS ---
# class AuthRequest(BaseModel):
#     email: EmailStr
#     password: str

# class VideoRequest(BaseModel):
#     url: str
#     language: str

# class ChatRequest(BaseModel):
#     task_id: str
#     question: str
    
# class VideoAnalysisSchema(BaseModel):
#     title: str = Field(description="A concise catchy title for the video presentation.")
#     summary: str = Field(description="A high-level comprehensive bullet-pointed outline paragraph summary.")
#     action_items: List[str] = Field(description="A list of action items, technical assignments, or tasks.")
#     key_decisions: List[str] = Field(description="A list of core architectures, frameworks chosen, or agreements resolved.")
#     open_questions: List[str] = Field(description="A list of unresolved questions, confusing definitions, or follow-ups.")

# # --- SIMULATED MOCK UPLOAD FOR PIPELINE CONCURRENT STRESS TESTING ---
# @app.post("/api/test-load-upload", status_code=status.HTTP_202_ACCEPTED)
# async def test_load_upload(
#     background_tasks: BackgroundTasks,
#     language: str = "english"
# ):
#     source_test_asset = "/app/temp_uploads/sample_test.mp4"
#     if not os.path.exists(source_test_asset):
#         raise HTTPException(
#             status_code=500, 
#             detail=f"Testing asset not found on container disk path at: {source_test_asset}"
#         )

#     task_id = str(uuid.uuid4())
#     tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
#     os.makedirs("temp_uploads", exist_ok=True)
#     temporary_video_path = f"temp_uploads/{task_id}.mp4"
#     shutil.copy(source_test_asset, temporary_video_path)
    
#     mock_user_id = "load_test_user_66"
#     background_tasks.add_task(async_local_video_worker, task_id, mock_user_id, temporary_video_path, language.lower().strip())
#     return {"task_id": task_id, "status": "processing"}

# # --- PRODUCTION CACHE CLEANUP ON SERVER STARTUP ---
# @app.on_event("startup")
# def startup_clean_cached_files():
#     cache_dirs = ["downloads", "temp_uploads"]
#     logger.info("🧹 Initializing startup disk storage housecleaning sweeps...")
#     for folder in cache_dirs:
#         if os.path.exists(folder):
#             try:
#                 for filename in os.listdir(folder):
#                     file_path = os.path.join(folder, filename)
#                     if os.path.isfile(file_path) or os.path.islink(file_path):
#                         os.remove(file_path)
#                     elif os.path.isdir(file_path):
#                         shutil.rmtree(file_path)
#                 logger.info(f"✅ Successfully emptied temporary directory: '{folder}/'")
#             except Exception as e:
#                 logger.error(f"⚠️ Problem clearing remnants out of '{folder}': {str(e)}")
#         else:
#             os.makedirs(folder, exist_ok=True)
#             logger.info(f"📁 Created missing operational folder container: '{folder}/'")
    
# # --- RUNNABLE EXTRACTION ENGINE WITH DYNAMIC ENHANCED MULTI-MODEL FALLBACKS ---
# def execute_safe_single_pass(transcript_str: str) -> VideoAnalysisSchema:
#     prompt = f"Analyze this video transcript and extract all metadata requirements cleanly:\n{transcript_str}"
    
#     # Define our priority chain tier tracking sequence array
#     models_pool = [
#         {"name": "Primary (Mistral AI)", "engine": Shared_llm},
#         {"name": "Fallback 1 (Groq Llama 3.3)", "engine": Groq_llm},
#         {"name": "Fallback 2 (OpenRouter Gemini)", "engine": OpenRouter_llm}
#     ]
    
#     last_error = None
    
#     for idx, model_node in enumerate(models_pool):
#         model_name = model_node["name"]
#         llm_instance = model_node["engine"]
        
#         # Exponential backoff retry loops inside each specific layer to tolerate transient pipeline strain
#         max_retries = 2
#         for attempt in range(max_retries):
#             try:
#                 logger.info(f"⚡ Attempting structured extraction via provider: {model_name} (Attempt {attempt + 1})")
                
#                 # Bind target schema using LangChain's native structure injection hook
#                 structured_llm = llm_instance.with_structured_output(VideoAnalysisSchema)
#                 result = structured_llm.invoke(prompt)
                
#                 # Resiliency check against NoneType structured responses
#                 if result is not None and getattr(result, "title", None):
#                     logger.info(f"🎉 Extraction task successfully fulfilled by provider: {model_name}")
#                     return result
                
#                 raise ValueError("Structured model response evaluation processed as empty target payload or NoneType.")
                
#             except Exception as e:
#                 last_error = str(e)
#                 logger.warning(f"⚠️ Provider framework failure: {model_name} on attempt {attempt + 1} -> Error: {last_error}")
#                 if attempt < max_retries - 1:
#                     sleep_time = (2 ** attempt) + random.uniform(0, 1)
#                     time.sleep(sleep_time)
        
#         logger.error(f"❌ Core engine layer completely exhausted for provider tier: {model_name}. Transitioning to next available asset...")
        
#     raise RuntimeError(f"All available backup language generation units failed execution pipeline limits. Last tracked error context: {last_error}")

# # --- AUTH ENDPOINTS ---
# @app.post("/api/auth/signup")
# def signup(payload: AuthRequest):
#     if users_col.find_one({"email": payload.email}):
#         raise HTTPException(status_code=400, detail="An account with this email already exists.")
    
#     users_col.insert_one({
#         "email": payload.email,
#         "hashed_password": hash_password(payload.password),
#         "created_at": datetime.utcnow()
#     })
#     return {"message": "Account created successfully. You can now log in!"}

# @app.post("/api/auth/login")
# def login(payload: AuthRequest):
#     user = users_col.find_one({"email": payload.email})
#     if not user or not verify_password(payload.password, user["hashed_password"]):
#         raise HTTPException(status_code=400, detail="Invalid email or password.")
    
#     access_token = create_access_token(data={"sub": user["email"]})
#     return {"access_token": access_token, "token_type": "bearer"}

# # --- BACKGROUND WORKERS (NATIVE MONGODB STATUS TRACKING) ---
# def async_video_processing_worker(task_id: str, user_id: str, source_url: str, language: str):
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
#         action_items = analysis_result.action_items
#         key_decisions = analysis_result.key_decisions
#         open_questions = analysis_result.open_questions

#         action_items_str = "\n".join([f"- {str(item).strip()}" for item in action_items if str(item).strip()])
#         key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in key_decisions if str(item).strip()])
#         open_questions_str = "\n".join([f"- {str(item).strip()}" for item in open_questions if str(item).strip()])

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

# def async_local_video_worker(task_id: str, user_id: str, temporary_video_path: str, language: str):
#     chunks_created = []
#     clean_video_filename = os.path.basename(temporary_video_path)
#     try:
#         chunks_created = process_local_input(temporary_video_path)
#         timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
#         if not timestamped_segments:
#             raise ValueError("No transcript segments generated from local media track.")

#         master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
#         build_vector_store(timestamped_segments, task_id=task_id)

#         logger.info(f"🤖 Running Forced Single-Pass Unified Extraction Profile for Local Task: {task_id}")
#         analysis_result = execute_safe_single_pass(master_transcript_str)
            
#         title = analysis_result.title.strip() if analysis_result.title else clean_video_filename
#         summary = analysis_result.summary.strip() if analysis_result.summary else "Summary generation empty."
#         action_items = analysis_result.action_items or []
#         key_decisions = analysis_result.key_decisions or []
#         open_questions = analysis_result.open_questions or []

#         action_items_str = "\n".join([f"- {str(item).strip()}" for item in action_items if str(item).strip()])
#         key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in key_decisions if str(item).strip()])
#         open_questions_str = "\n".join([f"- {str(item).strip()}" for item in open_questions if str(item).strip()])

#         analyses_col.insert_one({
#             "_id": task_id,
#             "user_id": user_id,
#             "video_url": "Local Uploaded File",
#             "title": title,
#             "summary": summary,
#             "action_items": action_items_str.strip(),
#             "key_decisions": key_decisions_str.strip(),
#             "open_questions": open_questions_str.strip(),
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

# # --- PIPELINE ENDPOINTS ---
# @app.post("/api/process-video", status_code=status.HTTP_202_ACCEPTED)
# async def process_video(payload: VideoRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
#     task_id = str(uuid.uuid4())
#     tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
#     background_tasks.add_task(async_video_processing_worker, task_id, current_user["id"], payload.url, payload.language.lower().strip())
#     return {"task_id": task_id, "status": "processing"}

# @app.get("/api/task-status/{task_id}")
# async def get_task_status(task_id: str):
#     task_info = tasks_col.find_one({"_id": task_id})
#     if task_info:
#         if task_info["status"] == "processing":
#             return {"status": "processing"}
#         if task_info["status"] == "failed":
#             return {"status": "failed", "error": task_info.get("error")}

#     record = analyses_col.find_one({"_id": task_id})
#     if record:
#         return {
#             "status": "completed",
#             "title": record["title"],
#             "summary": record["summary"],
#             "action_items": record["action_items"],
#             "key_decisions": record["key_decisions"],
#             "open_questions": record["open_questions"]
#         }
#     raise HTTPException(status_code=404, detail="Task or analysis profile index tracking entry not found.")

# @app.get("/api/history")
# def get_user_history(current_user: dict = Depends(get_current_user)):
#     history = analyses_col.find({"user_id": current_user["id"]}).sort("created_at", -1)
#     return [
#         {
#             "task_id": item["_id"],
#             "title": item["title"],
#             "video_url": item["video_url"],
#             "created_at": item.get("created_at", datetime.utcnow()).strftime("%Y-%m-%d")
#         } for item in history
#     ]

# @app.post("/api/chat")
# async def chat_with_video(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
#     record = analyses_col.find_one({"_id": payload.task_id})
#     if not record:
#         raise HTTPException(status_code=404, detail="Analysis context target not found inside database storage.")

#     try:
#         rag_chain = load_rag_chain(task_id=payload.task_id)
#         answer = await run_in_threadpool(ask_question, rag_chain, payload.question)
        
#         chats_col.insert_many([
#             {"analysis_id": payload.task_id, "sender": "user", "text": payload.question, "timestamp": datetime.utcnow()},
#             {"analysis_id": payload.task_id, "sender": "ai", "text": answer, "timestamp": datetime.utcnow()}
#         ])
#         return {"answer": answer}
#     except Exception as e:
#         logger.error(f"Chat pipeline processing failed -> {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/chat-history/{task_id}")
# def get_chat_history(task_id: str, current_user: dict = Depends(get_current_user)):
#     record = analyses_col.find_one({"_id": task_id})
#     if not record:
#         raise HTTPException(status_code=404, detail="Analysis profile not found.")
        
#     messages = chats_col.find({"analysis_id": task_id}).sort("timestamp", 1)
#     return [{"sender": msg["sender"], "text": msg["text"]} for msg in messages]

# @app.post("/api/upload-video", status_code=status.HTTP_202_ACCEPTED)
# async def upload_local_video(
#     background_tasks: BackgroundTasks,
#     file: UploadFile = File(...),
#     language: str = "english",
#     current_user: dict = Depends(get_current_user)
# ):
#     allowed_extensions = [".mp4", ".mkv", ".avi", ".mp3", ".wav", ".m4a"]
#     file_ext = os.path.splitext(file.filename)[1].lower()
#     if file_ext not in allowed_extensions:
#         raise HTTPException(status_code=400, detail="Unsupported file extension format.")

#     task_id = str(uuid.uuid4())
#     tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
#     os.makedirs("temp_uploads", exist_ok=True)
#     temporary_video_path = f"temp_uploads/{task_id}{file_ext}"
    
#     with open(temporary_video_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)
        
#     background_tasks.add_task(async_local_video_worker, task_id, current_user["id"], temporary_video_path, language.lower().strip())
#     return {"task_id": task_id, "status": "processing"}


import os
import uuid
import logging
import time
import random
from typing import Dict, Any, List
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
import shutil

# Core RAG/Extraction Imports
from app.utils.audio_processor import process_input, process_local_input
from app.core.transcriber import transcribe_all
from app.core.summarize import rate_limit_safe_llm
from app.core.vector_store import build_vector_store
from app.core.rag_engine import load_rag_chain, ask_question
from app.core.config import settings, db, Shared_llm, Groq_llm, OpenRouter_llm

# MongoDB Auth Collections & Helpers
from app.core.auth import get_current_user, hash_password, verify_password, create_access_token, users_col, analyses_col, chats_col

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Assistant Authenticated API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks_col = db[settings.TASKS_COLLECTION]

# --- SCHEMAS ---
class AuthRequest(BaseModel):
    email: EmailStr
    password: str

class VideoRequest(BaseModel):
    url: str
    language: str

class ChatRequest(BaseModel):
    task_id: str
    question: str
    
class VideoAnalysisSchema(BaseModel):
    title: str = Field(description="A concise catchy title for the video presentation.")
    summary: str = Field(description="A high-level comprehensive bullet-pointed outline paragraph summary.")
    action_items: List[str] = Field(description="A list of action items, technical assignments, or tasks.")
    key_decisions: List[str] = Field(description="A list of core architectures, frameworks chosen, or agreements resolved.")
    open_questions: List[str] = Field(description="A list of unresolved questions, confusing definitions, or follow-ups.")

# --- SIMULATED MOCK UPLOAD FOR PIPELINE CONCURRENT STRESS TESTING ---
@app.post("/api/test-load-upload", status_code=status.HTTP_202_ACCEPTED)
async def test_load_upload(
    background_tasks: BackgroundTasks,
    language: str = "english"
):
    source_test_asset = "/app/temp_uploads/sample_test.mp4"
    if not os.path.exists(source_test_asset):
        raise HTTPException(
            status_code=500, 
            detail=f"Testing asset not found on container disk path at: {source_test_asset}"
        )

    task_id = str(uuid.uuid4())
    tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
    os.makedirs("temp_uploads", exist_ok=True)
    temporary_video_path = f"temp_uploads/{task_id}.mp4"
    shutil.copy(source_test_asset, temporary_video_path)
    
    mock_user_id = "load_test_user_66"
    background_tasks.add_task(async_local_video_worker, task_id, mock_user_id, temporary_video_path, language.lower().strip())
    return {"task_id": task_id, "status": "processing"}

# --- PRODUCTION LIFECYCLE MANAGEMENT ON STARTUP ---
@app.on_event("startup")
def startup_lifecycle_initialization():
    # 1. Clear Orphaned Temp Audio/Video Fragments
    cache_dirs = ["downloads", "temp_uploads"]
    logger.info("🧹 Initializing startup disk storage housecleaning sweeps...")
    for folder in cache_dirs:
        if os.path.exists(folder):
            try:
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                logger.info(f"✅ Successfully emptied temporary directory: '{folder}/'")
            except Exception as e:
                logger.error(f"⚠️ Problem clearing remnants out of '{folder}': {str(e)}")
        else:
            os.makedirs(folder, exist_ok=True)
            logger.info(f"📁 Created missing operational folder container: '{folder}/'")

    # 2. Automated Database Index Compilation (Priority 1 Optimization)
    try:
        logger.info("⚡ Injecting MongoDB structural performance indices...")
        
        # Accelerate /api/history query paths sorting by user and creation dates
        analyses_col.create_index([("user_id", 1), ("created_at", -1)])
        
        # Accelerate workspace email collision validations inside signup routes
        users_col.create_index("email", unique=True)
        
        # Accelerate /api/chat-history chronological sequence reconstructions
        chats_col.create_index([("analysis_id", 1), ("timestamp", 1)])
        
        logger.info("🎉 MongoDB performance index compilation completed successfully.")
    except Exception as e:
        logger.error(f"⚠️ Index initialization error encountered: {str(e)}")

# --- RUNNABLE EXTRACTION ENGINE WITH DYNAMIC ENHANCED MULTI-MODEL FALLBACKS ---
def execute_safe_single_pass(transcript_str: str) -> VideoAnalysisSchema:
    prompt = f"Analyze this video transcript and extract all metadata requirements cleanly:\n{transcript_str}"
    
    models_pool = [
        {"name": "Primary (Mistral AI)", "engine": Shared_llm},
        {"name": "Fallback 1 (Groq Llama 3.3)", "engine": Groq_llm},
        {"name": "Fallback 2 (OpenRouter Gemini)", "engine": OpenRouter_llm}
    ]
    
    last_error = None
    
    for idx, model_node in enumerate(models_pool):
        model_name = model_node["name"]
        llm_instance = model_node["engine"]
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"⚡ Attempting structured extraction via provider: {model_name} (Attempt {attempt + 1})")
                structured_llm = llm_instance.with_structured_output(VideoAnalysisSchema)
                result = structured_llm.invoke(prompt)
                
                if result is not None and getattr(result, "title", None):
                    logger.info(f"🎉 Extraction task successfully fulfilled by provider: {model_name}")
                    return result
                
                raise ValueError("Structured model response evaluation processed as empty target payload or NoneType.")
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ Provider framework failure: {model_name} on attempt {attempt + 1} -> Error: {last_error}")
                if attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(sleep_time)
        
        logger.error(f"❌ Core engine layer completely exhausted for provider tier: {model_name}. Transitioning to next available asset...")
        
    raise RuntimeError(f"All available backup language generation units failed execution pipeline limits. Last tracked error context: {last_error}")

# --- AUTH ENDPOINTS ---
@app.post("/api/auth/signup")
def signup(payload: AuthRequest):
    if users_col.find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    
    users_col.insert_one({
        "email": payload.email,
        "hashed_password": hash_password(payload.password),
        "created_at": datetime.utcnow()
    })
    return {"message": "Account created successfully. You can now log in!"}

@app.post("/api/auth/login")
def login(payload: AuthRequest):
    user = users_col.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Invalid email or password.")
    
    access_token = create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

# --- BACKGROUND WORKERS (NATIVE MONGODB STATUS TRACKING) ---
def async_video_processing_worker(task_id: str, user_id: str, source_url: str, language: str):
    chunks_created = []
    try:
        chunks_created = process_input(source_url)
        timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
        if not timestamped_segments:
            raise ValueError("No transcript segments generated.")

        master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
        build_vector_store(timestamped_segments, task_id=task_id)

        logger.info(f"🤖 Running Forced Single-Pass Unified Extraction Profile for Task: {task_id}")
        analysis_result = execute_safe_single_pass(master_transcript_str)
            
        title = analysis_result.title.strip()
        summary = analysis_result.summary.strip()
        action_items = analysis_result.action_items
        key_decisions = analysis_result.key_decisions
        open_questions = analysis_result.open_questions

        action_items_str = "\n".join([f"- {str(item).strip()}" for item in action_items if str(item).strip()])
        key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in key_decisions if str(item).strip()])
        open_questions_str = "\n".join([f"- {str(item).strip()}" for item in open_questions if str(item).strip()])

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

def async_local_video_worker(task_id: str, user_id: str, temporary_video_path: str, language: str):
    chunks_created = []
    clean_video_filename = os.path.basename(temporary_video_path)
    try:
        chunks_created = process_local_input(temporary_video_path)
        timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
        if not timestamped_segments:
            raise ValueError("No transcript segments generated from local media track.")

        master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])
        build_vector_store(timestamped_segments, task_id=task_id)

        logger.info(f"🤖 Running Forced Single-Pass Unified Extraction Profile for Local Task: {task_id}")
        analysis_result = execute_safe_single_pass(master_transcript_str)
            
        title = analysis_result.title.strip() if analysis_result.title else clean_video_filename
        summary = analysis_result.summary.strip() if analysis_result.summary else "Summary generation empty."
        action_items = analysis_result.action_items or []
        key_decisions = analysis_result.key_decisions or []
        open_questions = analysis_result.open_questions or []

        action_items_str = "\n".join([f"- {str(item).strip()}" for item in action_items if str(item).strip()])
        key_decisions_str = "\n".join([f"- {str(item).strip()}" for item in key_decisions if str(item).strip()])
        open_questions_str = "\n".join([f"- {str(item).strip()}" for item in open_questions if str(item).strip()])

        analyses_col.insert_one({
            "_id": task_id,
            "user_id": user_id,
            "video_url": "Local Uploaded File",
            "title": title,
            "summary": summary,
            "action_items": action_items_str.strip(),
            "key_decisions": key_decisions_str.strip(),
            "open_questions": open_questions_str.strip(),
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

# --- PIPELINE ENDPOINTS ---
@app.post("/api/process-video", status_code=status.HTTP_202_ACCEPTED)
async def process_video(payload: VideoRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    task_id = str(uuid.uuid4())
    tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    background_tasks.add_task(async_video_processing_worker, task_id, current_user["id"], payload.url, payload.language.lower().strip())
    return {"task_id": task_id, "status": "processing"}

@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str):
    task_info = tasks_col.find_one({"_id": task_id})
    if task_info:
        if task_info["status"] == "processing":
            return {"status": "processing"}
        if task_info["status"] == "failed":
            return {"status": "failed", "error": task_info.get("error")}

    record = analyses_col.find_one({"_id": task_id})
    if record:
        return {
            "status": "completed",
            "title": record["title"],
            "summary": record["summary"],
            "action_items": record["action_items"],
            "key_decisions": record["key_decisions"],
            "open_questions": record["open_questions"]
        }
    raise HTTPException(status_code=404, detail="Task or analysis profile index tracking entry not found.")

@app.get("/api/history")
def get_user_history(current_user: dict = Depends(get_current_user)):
    history = analyses_col.find({"user_id": current_user["id"]}).sort("created_at", -1)
    return [
        {
            "task_id": item["_id"],
            "title": item["title"],
            "video_url": item["video_url"],
            "created_at": item.get("created_at", datetime.utcnow()).strftime("%Y-%m-%d")
        } for item in history
    ]

@app.post("/api/chat")
async def chat_with_video(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    record = analyses_col.find_one({"_id": payload.task_id})
    if not record:
        raise HTTPException(status_code=404, detail="Analysis context target not found inside database storage.")

    try:
        rag_chain = load_rag_chain(task_id=payload.task_id)
        answer = await run_in_threadpool(ask_question, rag_chain, payload.question)
        
        chats_col.insert_many([
            {"analysis_id": payload.task_id, "sender": "user", "text": payload.question, "timestamp": datetime.utcnow()},
            {"analysis_id": payload.task_id, "sender": "ai", "text": answer, "timestamp": datetime.utcnow()}
        ])
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Chat pipeline processing failed -> {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat-history/{task_id}")
def get_chat_history(task_id: str, current_user: dict = Depends(get_current_user)):
    record = analyses_col.find_one({"_id": task_id})
    if not record:
        raise HTTPException(status_code=404, detail="Analysis profile not found.")
        
    messages = chats_col.find({"analysis_id": task_id}).sort("timestamp", 1)
    return [{"sender": msg["sender"], "text": msg["text"]} for msg in messages]

@app.post("/api/upload-video", status_code=status.HTTP_202_ACCEPTED)
async def upload_local_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = "english",
    current_user: dict = Depends(get_current_user)
):
    allowed_extensions = [".mp4", ".mkv", ".avi", ".mp3", ".wav", ".m4a"]
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file extension format.")

    task_id = str(uuid.uuid4())
    tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
    os.makedirs("temp_uploads", exist_ok=True)
    temporary_video_path = f"temp_uploads/{task_id}{file_ext}"
    
    with open(temporary_video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    background_tasks.add_task(async_local_video_worker, task_id, current_user["id"], temporary_video_path, language.lower().strip())
    return {"task_id": task_id, "status": "processing"}