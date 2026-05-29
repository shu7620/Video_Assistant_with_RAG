import os
import uuid
import logging
from typing import Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime

# Core RAG/Extraction Imports
from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.summarize import summarize_transcript, generate_title
from core.extractor import extract_action_items, extract_key_decisions, extract_questions
from core.vector_store import build_vector_store
from core.rag_engine import load_rag_chain, ask_question

# New Auth & DB Imports
from core.auth import get_db, hash_password, verify_password, create_access_token, get_current_user, UserModel, AnalysisModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Video Assistant Authenticated API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Still using tasks_db to keep track of transient background loading tasks
tasks_db: Dict[str, Dict[str, Any]] = {}

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

# --- AUTH ENDPOINTS ---
@app.post("/api/auth/signup")
def signup(payload: AuthRequest, db: Session = Depends(get_db)):
    existing_user = db.query(UserModel).filter(UserModel.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    
    new_user = UserModel(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(new_user)
    db.commit()
    return {"message": "Account created successfully. You can now log in!"}

@app.post("/api/auth/login")
def login(payload: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid email or password.")
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# --- BACKGROUND WORKER ENGINE ---
# def async_video_processing_worker(task_id: str, user_id: int, source_url: str, language: str):
#     chunks_created = []
#     try:
#         chunks_created = process_input(source_url)
#         master_transcript = transcribe_all(chunks_created, language=language)
        
#         if not master_transcript.strip():
#             raise ValueError("Empty text transcript generated.")

#         db_storage_path = f"vector_db_{task_id}"
#         build_vector_store(master_transcript, persist_dir=db_storage_path)

#         video_title = generate_title(master_transcript)
#         video_summary = summarize_transcript(master_transcript)
#         action_items_str = extract_action_items(master_transcript)
#         key_decisions_str = extract_key_decisions(master_transcript)
#         open_questions_str = extract_questions(master_transcript)

#         # Write analysis to SQLite database persistently!
#         db = next(get_db())
#         db_analysis = AnalysisModel(
#             id=task_id,
#             user_id=user_id,
#             video_url=source_url,
#             title=video_title.strip(),
#             summary=video_summary.strip(),
#             action_items=action_items_str.strip(),
#             key_decisions=key_decisions_str.strip(),
#             open_questions=open_questions_str.strip(),
#             vector_db_path=db_storage_path
#         )
#         db.add(db_analysis)
#         db.commit()

#         # Mark in memory tracker as completed
#         tasks_db[task_id] = {"status": "completed"}

#     except Exception as e:
#         logger.error(f"Task failure -> {str(e)}")
#         tasks_db[task_id] = {"status": "failed", "error": str(e)}
#     finally:
#         for chunk_file in chunks_created:
#             if os.path.exists(chunk_file):
#                 os.remove(chunk_file)

#-----------------------------------------------------------------------------------------------------------------------------


def async_video_processing_worker(task_id: str, user_id: int, source_url: str, language: str):
    chunks_created = []
    try:
        # 1. Download & Slice Audio chunks (default is 10 min blocks)
        chunks_created = process_input(source_url)
        
        # 2. Get timestamped text segment dictionaries
        # Returns: [{"start": 0.0, "end": 4.5, "text": "Hello..."}, ...]
        timestamped_segments = transcribe_all(chunks_created, language=language, chunk_minutes=10)
        
        if not timestamped_segments:
            raise ValueError("No transcript segments generated.")

        # 3. Compile a plain text string for old legacy summary/extractor scripts
        master_transcript_str = "\n".join([f"[{seg['start']}] {seg['text']}" for seg in timestamped_segments])

        # 4. Build the modern vector store containing the timestamped metadata!
        db_storage_path = f"vector_db_{task_id}"
        build_vector_store(timestamped_segments, persist_dir=db_storage_path)

        # 5. Extract summaries and elements as usual using the text string
        video_title = generate_title(master_transcript_str)
        video_summary = summarize_transcript(master_transcript_str)
        action_items_str = extract_action_items(master_transcript_str)
        key_decisions_str = extract_key_decisions(master_transcript_str)
        open_questions_str = extract_questions(master_transcript_str)

        # 6. Save data to SQLite Database persistently
        db = next(get_db())
        db_analysis = AnalysisModel(
            id=task_id,
            user_id=user_id,
            video_url=source_url,
            title=video_title.strip(),
            summary=video_summary.strip(),
            action_items=action_items_str.strip(),
            key_decisions=key_decisions_str.strip(),
            open_questions=open_questions_str.strip(),
            vector_db_path=db_storage_path
        )
        db.add(db_analysis)
        db.commit()

        tasks_db[task_id] = {"status": "completed"}

    except Exception as e:
        logger.error(f"Task failure -> {str(e)}")
        tasks_db[task_id] = {"status": "failed", "error": str(e)}
    finally:
        for chunk_file in chunks_created:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)
                
                



# --- PROTECTED PIPELINE ENDPOINTS ---
@app.post("/api/process-video", status_code=status.HTTP_202_ACCEPTED)
async def process_video(payload: VideoRequest, background_tasks: BackgroundTasks, current_user: UserModel = Depends(get_current_user)):
    task_id = str(uuid.uuid4())
    tasks_db[task_id] = {"status": "processing"}
    
    background_tasks.add_task(
        async_video_processing_worker, 
        task_id, current_user.id, payload.url, payload.language.lower().strip()
    )
    return {"task_id": task_id, "status": "processing"}

@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str, db: Session = Depends(get_db)):
    # Check transient memory dictionary first
    if task_id in tasks_db:
        task_info = tasks_db[task_id]
        if task_info["status"] == "processing":
            return {"status": "processing"}
        if task_info["status"] == "failed":
            return {"status": "failed", "error": task_info.get("error")}

    # If completed or historical, grab directly from SQLite database
    record = db.query(AnalysisModel).filter(AnalysisModel.id == task_id).first()
    if record:
        return {
            "status": "completed",
            "title": record.title,
            "summary": record.summary,
            "action_items": record.action_items,
            "key_decisions": record.key_decisions,
            "open_questions": record.open_questions
        }
    
    raise HTTPException(status_code=404, detail="Task or analysis profile not found.")

@app.get("/api/history")
def get_user_history(current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieves all past analytical entries owned explicitly by the active authenticated user."""
    history = db.query(AnalysisModel).filter(AnalysisModel.user_id == current_user.id).all()
    return [
        {
            "task_id": item.id,
            "title": item.title,
            "video_url": item.video_url,
            "created_at": datetime.now().strftime("%Y-%m-%d") # Mock tracking date metric placeholder
        } for item in history
    ]

@app.post("/api/chat")
async def chat_with_video(payload: ChatRequest, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    record = db.query(AnalysisModel).filter(AnalysisModel.id == payload.task_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Analysis context target not found inside database storage.")

    try:
        rag_chain = load_rag_chain(persist_dir=record.vector_db_path)
        answer = ask_question(rag_chain, payload.question)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))