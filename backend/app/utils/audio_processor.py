import yt_dlp
from pydub import AudioSegment
import os

DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# Update ONLY this function inside utils/audio_processor.py

def download_youtube_audio(url: str) -> str:
    """Downloads audio from a YouTube video and saves it as a .wav file."""
    output_path = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    
    # Extract path from environment variable, falling back gracefully if missing
    # ffmpeg_env_path = os.getenv("FFMPEG_BINARY_PATH")
    # if not ffmpeg_env_path:
    #     ffmpeg_env_path = r"C:\Users\shubh\Downloads\ffmpeg-2026-05-25-git-34dfa8bf2b-full_build\bin"

    # ydl_opts = {
    #     "format": "bestaudio/best",
    #     "outtmpl": output_path,
    #     "ffmpeg_location": ffmpeg_env_path,  # 👈 Dynamic path assignment
    #     "postprocessors": [
    #         {
    #             "key": "FFmpegExtractAudio",
    #             "preferredcodec": "wav",
    #             "preferredquality": "192",
    #         }
    #     ],
    #     'cookiefile': 'www.youtube.com_cookies.txt',
    #     "quiet": True,
    # }

#     ydl_opts = {
#     "format": "bestaudio/best",
#     "outtmpl": output_path,
#     "postprocessors": [
#         {
#             "key": "FFmpegExtractAudio",
#             "preferredcodec": "wav",
#             "preferredquality": "192",
#         }
#     ],
#     "cookiefile": "www.youtube.com_cookies.txt",
#     "quiet": True,
# }
    ydl_opts = {
    "format": "bestaudio/best",

    "extractor_args": {
        "youtube": {
            "player_client": ["android"]
        }
    },

    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192",
        }
    ],

    "cookiefile": "www.youtube.com_cookies.txt",
    "quiet": True,
}
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # filename = ydl.prepare_filename(info).replace('.webm', '.wav').replace('.m4a', '.wav')
        original_file = ydl.prepare_filename(info)
        filename = os.path.splitext(original_file)[0] + ".wav"
    
    return filename


def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to a highly compressed 16kHz mono WAV file."""
    output_path = os.path.splitext(input_path)[0] + '_converted.wav'
    
    # Load the source video or audio container
    audio = AudioSegment.from_file(input_path)
    
    # Force single-channel (mono) and low sample rate (16kHz) which Whisper prefers
    audio = audio.set_channels(1).set_frame_rate(16000)
    
    # FIX: Explicitly restrict parameters to 16-bit PCM to radically compress file size
    audio.export(
        output_path, 
        format="wav", 
        parameters=["-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"]
    )
    
    return output_path

# Replace chunk_audio, process_input, and process_local_input in utils/audio_processor.py

def chunk_audio(wav_path: str, chunk_minutes: int = 10, overlap_minutes: float = 0.5) -> list:
    """
    Splits a WAV file into smaller chunks with a specified sliding overlap duration 
    to preserve boundary semantic context for the RAG pipeline.
    """
    audio = AudioSegment.from_wav(wav_path)
    
    chunk_ms = chunk_minutes * 60 * 1000
    overlap_ms = int(overlap_minutes * 60 * 1000)
    step_ms = chunk_ms - overlap_ms  # 👈 The magic line: how far forward we jump each time
    
    base_path, _ = os.path.splitext(wav_path)
    chunks = []
    
    # If the file is shorter than a single chunk, handle it immediately
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
        
        # If the next slice can't capture a meaningful frame past the overlap, we stop
        if end >= len(audio):
            break
            
        start += step_ms
        i += 1
    
    return chunks


def process_input(source: str) -> list:
    """Main pipeline function to process a remote YouTube source link."""
    if source.startswith("http://") or source.startswith("https://"):
        wav_path = download_youtube_audio(source)
    else:
        wav_path = convert_to_wav(source)

   
    # Explicitly using 10-minute chunks with 0.5-minute overlaps
    chunks = chunk_audio(wav_path, chunk_minutes=10, overlap_minutes=0.5)
   
    return chunks


def process_local_input(local_file_path: str) -> list:
    """Dedicated processor for handling multi-format local user file uploads."""
   
    standardized_wav = convert_to_wav(local_file_path)
    
    try:
        
        chunks = chunk_audio(standardized_wav, chunk_minutes=10, overlap_minutes=0.5)
        return chunks
    finally:
        if os.path.exists(standardized_wav):
            os.remove(standardized_wav)
