import os
import logging
from pydub import AudioSegment
from app.core.config import s3_client, settings

# 🌐 Initialize the logger module for container stream tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_file_to_s3(local_path: str, s3_key: str) -> str:
    """Uploads a file to the centralized S3 bucket securely."""
    s3_client.upload_file(
        Filename=local_path,
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=s3_key
    )
    return s3_key

def generate_s3_presigned_url(s3_key: str, expiration: int = 3600) -> str:
    """Generates a secure, temporary link for RAG analytics streaming access."""
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': s3_key},
        ExpiresIn=expiration
    )

def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to a highly compressed 16kHz mono WAV file."""
    output_path = os.path.splitext(input_path)[0] + '_converted.wav'
    
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000)
    
    audio.export(
        output_path, 
        format="wav", 
        parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"]
    )
    
    return output_path

def chunk_audio(wav_path: str, chunk_minutes: int = 10, overlap_minutes: float = 0.5) -> list:
    """Splits a WAV file into smaller chunks with sliding overlap duration."""
    audio = AudioSegment.from_wav(wav_path)
    
    chunk_ms = chunk_minutes * 60 * 1000
    overlap_ms = int(overlap_minutes * 60 * 1000)
    step_ms = chunk_ms - overlap_ms
    
    base_path, _ = os.path.splitext(wav_path)
    chunks = []
    
    if len(audio) <= chunk_ms:
        chunk_path = f"{base_path}_chunk_0.wav"
        audio.export(chunk_path, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"])
        return [chunk_path]

    start = 0
    i = 0
    while start < len(audio):
        end = start + chunk_ms
        chunk = audio[start:end]
        
        chunk_path = f"{base_path}_chunk_{i}.wav"
        chunk.export(chunk_path, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"])
        chunks.append(chunk_path)
        
        if end >= len(audio):
            break
            
        start += step_ms
        i += 1
    
    return chunks

def process_input(source: str) -> list:
    """Main pipeline function to process local files only."""
    if source.startswith(("http://", "https://")):
        raise ValueError(
            "YouTube URLs are no longer supported. Please upload a local audio/video file."
        )

    wav_path = convert_to_wav(source)
    chunks = chunk_audio(wav_path, chunk_minutes=10, overlap_minutes=0.5)
    return chunks

def process_local_input(local_file_path: str) -> list:
    """Dedicated processor for local files that copies tracking artifacts to cloud storage."""
    standardized_wav = convert_to_wav(local_file_path)
    
    try:
        chunks = chunk_audio(standardized_wav, chunk_minutes=10, overlap_minutes=0.5)
        
        s3_backed_keys = []
        for local_chunk in chunks:
            if not os.path.exists(local_chunk):
                logger.warning(f"⚠️ Local chunk file missing from disk path: {local_chunk}")
                continue
                
            filename = os.path.basename(local_chunk)
            s3_key = f"chunks/{filename}"
            
            logger.info(f"📤 Uploading chunk to S3: {s3_key}...")
            upload_file_to_s3(local_chunk, s3_key)
            s3_backed_keys.append(s3_key)
            
            if os.path.exists(local_chunk):
                os.remove(local_chunk)
                logger.info(f"🗑️ Cleaned up temporary local scratch space for: {filename}")
                
        return s3_backed_keys
    finally:
        if os.path.exists(standardized_wav):
            os.remove(standardized_wav)