import os
import sys
import requests
from pydub import AudioSegment
from dotenv import load_dotenv

import time
load_dotenv()

# Forcefully append your FFmpeg bin folder to Python's environment PATH
ffmpeg_dir = r"C:\Users\shubh\Downloads\ffmpeg-2026-05-25-git-34dfa8bf2b-full_build\bin"
if ffmpeg_dir not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + ffmpeg_dir

SARVAM_PIECE_SECONDS = 25
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")

# --- GROQ CLOUD ENDPOINT CONFIGURATIONS ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_AUDIO_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


import os
import time
import requests

def transcribe_chunk_whisper_groq(chunk_path: str, base_offset_seconds: float = 0.0) -> list:
    """
    Sends an audio track cleanly to Groq Cloud API, handling rate limits (HTTP 429) 
    gracefully with progressive exponential backoff retries.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing from environment or your configuration .env file")

    # Calculate actual file size dynamically for accurate logging
    file_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
    

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    
    # --- RATE LIMIT RETRY CONFIGURATION ---
    max_retries = 5          # Up to 5 retry attempts before raising a hard error
    initial_delay = 20       # Start with a 20-second pause (Groq RPM resets per minute)
    backoff_factor = 1.5     # Increase the wait time progressively if rate limits persist

    for attempt in range(max_retries):
        with open(chunk_path, "rb") as audio_file:
            files = {
                "file": (os.path.basename(chunk_path), audio_file, "audio/wav")
            }
            data = {
                "model": "whisper-large-v3",
                "response_format": "verbose_json",
                "language": "en"
            }

            try:
                response = requests.post(GROQ_AUDIO_URL, headers=headers, files=files, data=data, timeout=90)
            except requests.exceptions.RequestException as e:
                # Catch network disruptions/DNS issues and retry instead of crashing
                time.sleep(5)
                continue

        # Handle Rate Limiting (429 Too Many Requests)
        if response.status_code == 429:
            # Check if Groq passed an explicit retry instruction header, fallback to exponential calculation if not
            retry_after = response.headers.get("Retry-After")
            wait_time = float(retry_after) if retry_after else (initial_delay * (backoff_factor ** attempt))
            
            
            time.sleep(wait_time)
            continue

        # Raise exception for any other non-200 HTTP response profiles
        if response.status_code != 200:
            raise RuntimeError(f"Groq Cloud API Error {response.status_code}: {response.text}")

        # If execution hits here, response status is 200 OK -> break the loop safely!
        break
    else:
        # Executes only if the loop runs to exhaustion without reaching a 'break' statement
        raise RuntimeError(f"❌ Failed to transcribe file via Groq after {max_retries} progressive rate-limit retries.")

    api_response = response.json()
    segments_with_time = []

    # Map Groq's verbose timestamp structure straight into active RAG payload fields
    for seg in api_response.get("segments", []):
        segments_with_time.append({
            "start": base_offset_seconds + float(seg["start"]),
            "end": base_offset_seconds + float(seg["end"]),
            "text": seg["text"].strip()
        })

    return segments_with_time


def _send_to_sarvam(piece_path: str) -> dict:
    """Send one ≤30s WAV file to Sarvam API and ask for timestamp details."""
    headers = {"api-subscription-key": SARVAM_API_KEY}

    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        data = {
            "model": SARVAM_MODEL, 
            "with_diarization": "false",
            "mode": "translate",
            "with_timestamps": "true" 
        }
        
        response = requests.post(
            SARVAM_STT_TRANSLATE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )

    if not response.ok:
        print(f"\n❌ Sarvam returned {response.status_code}")
        response.raise_for_status()

    return response.json()


def transcribe_chunk_sarvam(chunk_path: str, base_offset_seconds: float = 0.0) -> list:
    """Fragments a macro chunk, pulls timestamps from Sarvam API, and normalizes them."""
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in environment / .env")

    audio = AudioSegment.from_wav(chunk_path)
    piece_ms = SARVAM_PIECE_SECONDS * 1000
    segments_with_time = []
    
    for i, start_ms in enumerate(range(0, len(audio), piece_ms)):
        piece = audio[start_ms: start_ms + piece_ms]
        piece_path = f"{chunk_path}_sv_{i}.wav"
        piece.export(piece_path, format="wav")

        piece_offset_seconds = base_offset_seconds + (start_ms / 1000.0)

        try:
            api_response = _send_to_sarvam(piece_path)
            for timestamped_item in api_response.get("timestamped_transcript", []):
                segments_with_time.append({
                    "start": piece_offset_seconds + (timestamped_item["start_time"] / 1000.0),
                    "end": piece_offset_seconds + (timestamped_item["end_time"] / 1000.0),
                    "text": timestamped_item["text"].strip()
                })
        finally:
            if os.path.exists(piece_path):
                os.remove(piece_path)

    return segments_with_time


def transcribe_all(chunks: list, language: str = "english", chunk_minutes: int = 10) -> list:
    """ chronological loop orchestrator routing to Groq or Sarvam API endpoints."""
    all_timestamped_segments = [] 
    engine = "Sarvam AI (Hindi/Hinglish API)" if language.lower() == "hinglish" else "Groq Cloud LPU (Whisper-v3 Endpoint)"
    
    
    # --- NEW: Define overlap timeline offset values ---
    overlap_minutes = 0.5
    step_minutes = chunk_minutes - overlap_minutes

    for i, chunk in enumerate(chunks):  
        
        base_offset_seconds = i * step_minutes * 60.0
        
        if language.lower() == "hinglish":
            chunk_segments = transcribe_chunk_sarvam(chunk, base_offset_seconds)
        else:
            chunk_segments = transcribe_chunk_whisper_groq(chunk, base_offset_seconds)
            
        all_timestamped_segments.extend(chunk_segments)

    
    return all_timestamped_segments