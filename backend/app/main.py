import os
import uuid
import logging
from typing import Dict, Any, List
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
import shutil
from langchain_mistralai import ChatMistralAI

# Core RAG/Extraction Imports
from app.utils.audio_processor import process_input, process_local_input
from app.core.transcriber import transcribe_all
from app.core.summarize import rate_limit_safe_llm
from app.core.vector_store import build_vector_store
from app.core.rag_engine import load_rag_chain, ask_question
from app.core.config import settings, db, Shared_llm

# MongoDB Auth Collections & Helpers
from app.core.auth import get_current_user, hash_password, verify_password, create_access_token, users_col, analyses_col, chats_col

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Assistant Authenticated API")

# Overhaul the CORSMiddleware implementation block:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Dynamically loads values from your .env file
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent Tasks collection instance mapping straight to MongoDB pool initialization
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
    
# --- PRODUCTION CACHE CLEANUP ON SERVER STARTUP ---
@app.on_event("startup")
def startup_clean_cached_files():
    """
    Sweeps your temporary directories cleanly upon application startup.
    This guarantees that orphaned file remnants don't slowly exhaust your server disk.
    """
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
    
# --- HELPER: SAFE SINGLE-PASS EXTRACTION EXECUTOR ---
def execute_safe_single_pass(transcript_str: str) -> VideoAnalysisSchema:
    """
    Isolates the LangChain runnable extraction execution block to ensure 
    the rate_limit_safe_llm decorator functions correctly.
    """
    structured_llm = Shared_llm.with_structured_output(VideoAnalysisSchema)
    prompt = f"Analyze this video transcript and extract all metadata requirements cleanly:\n{transcript_str}"
    
    # Define a localized wrapper function that our decorator can monitor safely
    @rate_limit_safe_llm(max_retries=5, initial_delay=15)
    def invoke_llm():
        return structured_llm.invoke(prompt)
        
    return invoke_llm()

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

        # Convert the Python lists cleanly into Markdown lists with type/existence checks
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
            
        title = analysis_result.title.strip()
        summary = analysis_result.summary.strip()
        action_items = analysis_result.action_items
        key_decisions = analysis_result.key_decisions
        open_questions = analysis_result.open_questions

        if not title or "error" in title.lower():
            title = clean_video_filename

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
