import os
import sys

# Forcefully append your FFmpeg bin folder to Python's environment PATH
ffmpeg_dir = r"C:\Users\shubh\Downloads\ffmpeg-2026-05-25-git-34dfa8bf2b-full_build\bin"  # <--- Change this to your actual ffmpeg bin folder path
if ffmpeg_dir not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + ffmpeg_dir

import whisper
import requests
from pydub import AudioSegment
import os
from dotenv import load_dotenv
load_dotenv()

# Sarvam's sync STT-translate API rejects audio longer than 30s.
# We slice each chunk into 25s pieces (with a 5s safety margin) before sending.
SARVAM_PIECE_SECONDS = 25

WHISPER_MODEL =os.getenv("WHISPER_MODEL","small")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")

_model=None

def load_model():
    
    global _model
    
    if _model is None:
        print("Loading Whisper Model...")
        _model=whisper.load_model(WHISPER_MODEL)
        print("Whisper model loaded successfully.")
        
    return _model


def transcribe_chunk_whisper(chunk_path: str) -> str:

    model = load_model()  

    result = model.transcribe(chunk_path, task="transcribe")  
    return result["text"]  



def _send_to_sarvam(piece_path: str) -> str:
    """Send one ≤30s WAV file to Sarvam API and return its English translation/transcript."""
    headers = {"api-subscription-key": SARVAM_API_KEY}

    # Open the audio file in binary mode and pack it into a multipart form data request
    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        data = {"model": SARVAM_MODEL, "with_diarization": "false","mode":"translate"}
        
        
        # Dispatch the HTTP POST request to Sarvam's Speech-to-Text translation endpoint
        response = requests.post(
            SARVAM_STT_TRANSLATE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )

    # Error handling for unexpected API rejections or failures
    if not response.ok:
        print(f"\n❌ Sarvam returned {response.status_code}")
        print(f"Response body: {response.text}\n")
        response.raise_for_status()

    # Parse and return the text transcription key from the JSON payload response
    return response.json().get("transcript", "")


def transcribe_chunk_sarvam(chunk_path: str) -> str:
    """
    Handles mixed-language/Hinglish transcription via Sarvam API.
    
    Sarvam's synchronous endpoint strictly enforces a 30-second maximum duration.
    This wrapper fragments a larger chunk into safe 25-second micro-pieces, 
    submits them sequentially, and chains the textual outputs.
    """
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in environment / .env")

    # Load the current macro chunk via pydub
    audio = AudioSegment.from_wav(chunk_path)
    piece_ms = SARVAM_PIECE_SECONDS * 1000

    full_text = ""
    # Calculate total sub-pieces needed using ceiling division
    total_pieces = (len(audio) + piece_ms - 1) // piece_ms

    # Slide through the audio array slice by slice
    for i, start in enumerate(range(0, len(audio), piece_ms)):
        piece = audio[start: start + piece_ms]
        piece_path = f"{chunk_path}_sv_{i}.wav"
        
        # Export the mini-file locally to act as our network payload
        piece.export(piece_path, format="wav")

        try:
            print(f"  → Sarvam piece {i + 1}/{total_pieces} ...")
            full_text += _send_to_sarvam(piece_path) + " "
        finally:
            # Clean up the temporary micro-audio file from disk immediately after use
            if os.path.exists(piece_path):
                os.remove(piece_path)

    return full_text.strip()


def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    """
    Routes a single audio chunk to the appropriate machine learning engine.
    - 'english'  → Processes locally via OpenAI Whisper.
    - 'hinglish' → Routes to Sarvam Cloud API for translation and transcription.
    """
    if language.lower() == "hinglish":
        return transcribe_chunk_sarvam(chunk_path)
    return transcribe_chunk_whisper(chunk_path)


def transcribe_all(chunks: list, language: str = "english") -> str:
    """
    Top-level orchestrator that iterates over a batch list of audio chunk paths,
    runs them through the designated pipeline engine, and merges them into a
    single unified master transcript string.
    """
    full_transcript = "" 

    # Identify and display the routing engine being used
    engine = "Sarvam AI (Hinglish/Translation)" if language.lower() == "hinglish" else "Whisper (Local English)"
    print(f"Using {engine} for transcription.")

    # Process each audio file block sequentially
    for i, chunk in enumerate(chunks):  
        print(f"Transcribing chunk {i + 1}/{len(chunks)}...")
        
        # Pass the file path to our processing router
        text = transcribe_chunk(chunk, language=language)  
        full_transcript += text + " "  

    print("Transcription complete.")
    return full_transcript.strip()