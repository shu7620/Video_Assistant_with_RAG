import os
import sys

# Forcefully append your FFmpeg bin folder to Python's environment PATH
ffmpeg_dir = r"C:\Users\shubh\Downloads\ffmpeg-2026-05-25-git-34dfa8bf2b-full_build\bin"
if ffmpeg_dir not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + ffmpeg_dir

import whisper
import requests
from pydub import AudioSegment
from dotenv import load_dotenv
load_dotenv()

SARVAM_PIECE_SECONDS = 25
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")

_model = None

def load_model():
    global _model
    if _model is None:
        print("Loading Whisper Model...")
        _model = whisper.load_model(WHISPER_MODEL)
        print("Whisper model loaded successfully.")
    return _model


def transcribe_chunk_whisper(chunk_path: str, base_offset_seconds: float = 0.0) -> list:
    """Processes audio locally via Whisper and returns segments with absolute timestamps."""
    model = load_model()  
    # Explicitly requesting word/segment level details
    result = model.transcribe(chunk_path, task="transcribe")  
    
    segments_with_time = []
    for seg in result.get("segments", []):
        segments_with_time.append({
            "start": base_offset_seconds + seg["start"],
            "end": base_offset_seconds + seg["end"],
            "text": seg["text"].strip()
        })
    return segments_with_time


def _send_to_sarvam(piece_path: str) -> dict:
    """Send one ≤30s WAV file to Sarvam API and ask for timestamp details."""
    headers = {"api-subscription-key": SARVAM_API_KEY}

    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        # CRITICAL CHANGE: added 'with_timestamps': 'true'
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

        # Track the absolute starting point of this sub-slice in the entire video
        piece_offset_seconds = base_offset_seconds + (start_ms / 1000.0)

        try:
            api_response = _send_to_sarvam(piece_path)
            
            # Sarvam v3 returns timestamped words/phrases inside the response
            # Adjusting their relative time offsets to match the total video length
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
    """
    Orchestrates the chronological looping of video audio blocks.
    Returns a combined list of segment dicts carrying text and timestamps.
    """
    all_timestamped_segments = [] 
    engine = "Sarvam AI (Hinglish)" if language.lower() == "hinglish" else "Whisper (Local English)"
    print(f"Using {engine} for timestamp-aware transcription.")

    for i, chunk in enumerate(chunks):  
        print(f"Transcribing chunk {i + 1}/{len(chunks)}...")
        
        # Calculate how many seconds into the video this chunk starts
        # assuming the audio_processor chunks are exactly chunk_minutes long
        base_offset_seconds = i * chunk_minutes * 60.0
        
        if language.lower() == "hinglish":
            chunk_segments = transcribe_chunk_sarvam(chunk, base_offset_seconds)
        else:
            chunk_segments = transcribe_chunk_whisper(chunk, base_offset_seconds)
            
        all_timestamped_segments.extend(chunk_segments)

    print(f"Transcription complete. Extracted {len(all_timestamped_segments)} timed segments.")
    return all_timestamped_segments