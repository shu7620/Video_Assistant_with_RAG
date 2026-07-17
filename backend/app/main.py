
# import os
# import uuid
# import logging
# from typing import Dict, Any, List
# from fastapi import FastAPI, HTTPException, status, Depends, UploadFile, File
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.concurrency import run_in_threadpool
# from pydantic import BaseModel, EmailStr, Field
# from datetime import datetime
# import shutil
# import ast

# # Core Configurations
# from app.core.config import settings, db
# from app.core.auth import get_current_user, hash_password, verify_password, create_access_token, users_col, analyses_col, chats_col
# from app.core.rag_engine import load_rag_chain, ask_question

# # Celery task distribution import hooks
# from app.celery_worker import process_remote_video_task, process_local_video_task

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# app = FastAPI(title="AI Video Assistant Authenticated API")

# # 1. Fallback base domains list
# origins = ["https://www.transcribex.me", "https://transcribex.me"]

# # 2. Try to append domains dynamically from environment settings if present
# raw_origins = os.getenv("ALLOWED_ORIGINS")
# if raw_origins:
#     try:
#         parsed_origins = ast.literal_eval(raw_origins)
#         if isinstance(parsed_origins, list):
#             origins = list(set(origins + [str(o) for o in parsed_origins]))
#     except (ValueError, SyntaxError):
#         # Fallback splitting by comma if formatted as plain text split strings
#         extra_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
#         origins = list(set(origins + extra_origins))

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
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

# # --- SIMULATED MOCK UPLOAD FOR PIPELINE CONCURRENT STRESS TESTING ---
# @app.post("/api/test-load-upload", status_code=status.HTTP_202_ACCEPTED)
# async def test_load_upload(language: str = "english"):
#     # Target path within the shared container storage volume context
#     source_test_asset = "temp_uploads/sample_test.mp4"
#     if not os.path.exists(source_test_asset):
#         raise HTTPException(
#             status_code=500, 
#             detail=f"Testing asset not found on container disk path at: {source_test_asset}"
#         )

#     task_id = str(uuid.uuid4())
#     tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
#     temporary_video_path = f"temp_uploads/{task_id}.mp4"
#     shutil.copy(source_test_asset, temporary_video_path)
    
#     mock_user_id = "load_test_user_66"
    
#     # 🚀 OFFLOAD TO CELERY BROKER QUEUE INSTANTLY
#     process_local_video_task.delay(task_id, mock_user_id, temporary_video_path, language.lower().strip())
#     return {"task_id": task_id, "status": "processing"}

# # --- PRODUCTION LIFECYCLE MANAGEMENT ON STARTUP ---
# @app.on_event("startup")
# def startup_lifecycle_initialization():
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
#             except Exception as e:
#                 logger.error(f"⚠️ Problem clearing remnants out of '{folder}': {str(e)}")
#         else:
#             os.makedirs(folder, exist_ok=True)
            
#     try:
#         logger.info("⚡ Injecting MongoDB structural performance indices...")
#         analyses_col.create_index([("user_id", 1), ("created_at", -1)])
#         users_col.create_index("email", unique=True)
#         chats_col.create_index([("analysis_id", 1), ("timestamp", 1)])
#         logger.info("🎉 MongoDB performance index compilation completed successfully.")
#     except Exception as e:
#         logger.error(f"⚠️ Index initialization error encountered: {str(e)}")

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

# # --- PIPELINE ENDPOINTS ---
# @app.post("/api/process-video", status_code=status.HTTP_202_ACCEPTED)
# async def process_video(payload: VideoRequest, current_user: dict = Depends(get_current_user)):
#     task_id = str(uuid.uuid4())
#     tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
#     # 🚀 OFFLOAD TO CELERY BROKER QUEUE INSTANTLY
#     process_remote_video_task.delay(task_id, current_user["id"], payload.url, payload.language.lower().strip())
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
#     raise HTTPException(status_code=404, detail="Task or analysis entry not found.")

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
#         raise HTTPException(status_code=404, detail="Analysis context target not found.")

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
        
#     # 🚀 OFFLOAD TO CELERY BROKER QUEUE INSTANTLY
#     process_local_video_task.delay(task_id, current_user["id"], temporary_video_path, language.lower().strip())
#     return {"task_id": task_id, "status": "processing"}

import os
import uuid
import logging
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, status, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
import shutil
import ast

# Core Configurations
from app.core.config import settings, db, redis_client
from app.core.auth import get_current_user, hash_password, verify_password, create_access_token, users_col, analyses_col, chats_col
from app.core.rag_engine import load_rag_chain, ask_question

# Celery task distribution import hooks
from app.celery_worker import process_remote_video_task, process_local_video_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Assistant Authenticated API")

# 1. Fallback base domains list
origins = ["https://www.transcribex.me", "https://transcribex.me"]

# 2. Try to append domains dynamically from environment settings if present
raw_origins = os.getenv("ALLOWED_ORIGINS")
if raw_origins:
    try:
        parsed_origins = ast.literal_eval(raw_origins)
        if isinstance(parsed_origins, list):
            origins = list(set(origins + [str(o) for o in parsed_origins]))
    except (ValueError, SyntaxError):
        extra_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        origins = list(set(origins + extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks_col = db[settings.TASKS_COLLECTION]

# Max Video Upload Boundary Context (80 Megabytes)
MAX_FILE_SIZE = 80 * 1024 * 1024 

# --- INTERNAL RATE LIMITING HELPER ---
def check_rate_limit(user_id: str, endpoint: str):
    """Redis-backed rolling window rate-limiter to protect pipeline costs."""
    key = f"ratelimit:{user_id}:{endpoint}"
    current_requests = redis_client.incr(key)
    
    if current_requests == 1:
        # Set expiry window for the rolling frame on the first increment
        redis_client.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
        
    if current_requests > settings.MAX_REQUESTS_PER_WINDOW:
        logger.warning(f"🚨 Rate limit breached for user {user_id} on endpoint {endpoint}.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. You are allowed a maximum of {settings.MAX_REQUESTS_PER_WINDOW} requests every {settings.RATE_LIMIT_WINDOW_SECONDS} seconds."
        )

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

# --- SIMULATED MOCK UPLOAD FOR PIPELINE CONCURRENT STRESS TESTING ---
@app.post("/api/test-load-upload", status_code=status.HTTP_202_ACCEPTED)
async def test_load_upload(language: str = "english"):
    source_test_asset = "temp_uploads/sample_test.mp4"
    if not os.path.exists(source_test_asset):
        raise HTTPException(
            status_code=500, 
            detail=f"Testing asset not found on container disk path at: {source_test_asset}"
        )

    task_id = str(uuid.uuid4())
    tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
    temporary_video_path = f"temp_uploads/{task_id}.mp4"
    shutil.copy(source_test_asset, temporary_video_path)
    
    mock_user_id = "load_test_user_66"
    
    process_local_video_task.delay(task_id, mock_user_id, temporary_video_path, language.lower().strip())
    return {"task_id": task_id, "status": "processing"}

# --- PRODUCTION LIFECYCLE MANAGEMENT ON STARTUP ---
@app.on_event("startup")
def startup_lifecycle_initialization():
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
            except Exception as e:
                logger.error(f"⚠️ Problem clearing remnants out of '{folder}': {str(e)}")
        else:
            os.makedirs(folder, exist_ok=True)
            
    try:
        logger.info("⚡ Injecting MongoDB structural performance indices...")
        analyses_col.create_index([("user_id", 1), ("created_at", -1)])
        users_col.create_index("email", unique=True)
        chats_col.create_index([("analysis_id", 1), ("timestamp", 1)])
        logger.info("🎉 MongoDB performance index compilation completed successfully.")
    except Exception as e:
        logger.error(f"⚠️ Index initialization error encountered: {str(e)}")

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

# --- PIPELINE ENDPOINTS ---
@app.post("/api/process-video", status_code=status.HTTP_202_ACCEPTED)
async def process_video(payload: VideoRequest, current_user: dict = Depends(get_current_user)):
    # Apply API Cost/Rate Limit Guardrail Protection
    check_rate_limit(current_user["id"], "process-video")
    
    task_id = str(uuid.uuid4())
    tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
    process_remote_video_task.delay(task_id, current_user["id"], payload.url, payload.language.lower().strip())
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
    raise HTTPException(status_code=404, detail="Task or analysis entry not found.")

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
        raise HTTPException(status_code=404, detail="Analysis context target not found.")

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
    file: UploadFile = File(...),
    language: str = "english",
    current_user: dict = Depends(get_current_user)
):
    # Apply API Cost/Rate Limit Guardrail Protection
    check_rate_limit(current_user["id"], "upload-video")

    allowed_extensions = [".mp4", ".mkv", ".avi", ".mp3", ".wav", ".m4a"]
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file extension format.")

    task_id = str(uuid.uuid4())
    os.makedirs("temp_uploads", exist_ok=True)
    temporary_video_path = f"temp_uploads/{task_id}{file_ext}"
    
    total_bytes_written = 0
    try:
        with open(temporary_video_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                total_bytes_written += len(chunk)
                if total_bytes_written > MAX_FILE_SIZE:
                    logger.warning(f"❌ Upload rejected: File size limit exceeded {MAX_FILE_SIZE} bytes.")
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Uploaded file exceeds our maximum allowance limit of 80 Megabytes."
                    )
                buffer.write(chunk)
    except HTTPException:
        if os.path.exists(temporary_video_path):
            os.remove(temporary_video_path)
        raise
    except Exception as e:
        if os.path.exists(temporary_video_path):
            os.remove(temporary_video_path)
        logger.error(f"File writing streaming loop exception: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while streaming the upload to disk storage.")

    tasks_col.insert_one({"_id": task_id, "status": "processing", "created_at": datetime.utcnow()})
    
    process_local_video_task.delay(task_id, current_user["id"], temporary_video_path, language.lower().strip())
    return {"task_id": task_id, "status": "processing"}