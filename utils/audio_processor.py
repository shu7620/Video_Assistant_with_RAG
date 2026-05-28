import yt_dlp
from pydub import AudioSegment
import os


DOWNLOAD_DIR='downloads'
os.makedirs(DOWNLOAD_DIR,exist_ok=True)


def download_youtube_audio(url: str) -> str:
    """Downloads audio from a YouTube video and saves it as a .wav file."""
    
    # Define the output template for the downloaded file
    output_path = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    
    # Configure yt-dlp download and post-processing options
    ydl_opts = {
        "format": "bestaudio/best",  # Fetch the highest quality audio stream available
        "outtmpl": output_path,       # Set the destination path and filename format
        
        # 1. BYPASS WINDOWS PATH: Tell yt-dlp exactly where ffmpeg.exe is
        # Change this string to the exact folder where your ffmpeg binaries sit!
        "ffmpeg_location": r"C:\Users\shubh\Downloads\ffmpeg-2026-05-25-git-34dfa8bf2b-full_build\bin",
        "postprocessors": [
            {
                # Use FFmpeg to extract and convert the audio stream to WAV
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",  # Target bitrate quality (192 kbps)
            }
        ],
        "quiet": True,  # Suppress console output logs from yt-dlp
    }
    
    # Initialize yt-dlp with the specified configuration
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Download the video data and extract its metadata
        info = ydl.extract_info(url, download=True)
        
        # Predict the final filename and manually adjust the extension to .wav,
        # since the postprocessor changes it after yt-dlp handles the initial download.
        filename = ydl.prepare_filename(info).replace('.webm', '.wav').replace('.m4a', '.wav')
    
    return filename




def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to WAV format using pydub."""
    
    # Generate the output path by replacing the original extension with '_converted.wav'
    output_path = os.path.splitext(input_path)[0] + '_converted.wav'
    
    # Load the source audio or video file (pydub handles container decoding automatically)
    audio = AudioSegment.from_file(input_path)
    
    # Standardize audio properties for downstream processing (e.g., Speech-to-Text/RAG):
    # .set_channels(1) converts the audio to Mono (single channel)
    # .set_frame_rate(16000) downsamples/upsamples the frequency to 16kHz
    audio = audio.set_channels(1).set_frame_rate(16000)
    
    # Export the modified audio data as a standard WAV file
    audio.export(output_path, format="wav")
    
    return output_path



def chunk_audio(wav_path: str, chunk_minutes: int = 10) -> list:
    """Splits a WAV file into smaller chunks of specified duration (in minutes)."""
    
    # Load the WAV file into memory using pydub
    audio = AudioSegment.from_wav(wav_path)
    
    # Convert the requested chunk duration from minutes to milliseconds (pydub operates in ms)
    chunk_ms = chunk_minutes * 60 * 1000
    
    # Get the base file path without the '.wav' extension to avoid '.wav_chunk_0.wav' naming
    base_path, _ = os.path.splitext(wav_path)
    
    # Initialize an empty list to store the file paths of the generated chunks
    chunks = []
    
    # Iterate through the audio file in steps equal to the chunk duration
    for i, start in enumerate(range(0, len(audio), chunk_ms)):
        # Slice the audio segment from the start timestamp to the end of the chunk duration
        chunk = audio[start : start + chunk_ms]
        
        # Construct a clean output path (e.g., 'path/to/audio_chunk_0.wav')
        chunk_path = f"{base_path}_chunk_{i}.wav"
        
        # Export the sliced segment to the local disk as a standard WAV file
        chunk.export(chunk_path, format='wav')
        
        # Track the path of the newly created chunk file
        chunks.append(chunk_path)
    
    return chunks


def process_input(source: str) -> list:
    """Main pipeline function to process an input source (URL or local file),

    standardize it, and split it into manageable audio chunks for the RAG
    system.
    """

    # Check if the input source is a YouTube video url
    if source.startswith("http://") or source.startswith("https://"):
        print("Detected a YouTube url. Downloading audio...")
        wav_path = download_youtube_audio(source)
    else:
        # Otherwise, treat the input as a local file path (e.g., .mp3, .mp4, .m4a)
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    # Process the single, unified WAV file into smaller, fixed-length segments
    print("Chunking audio...")
    chunks = chunk_audio(wav_path)

    print(f"Audio ready — {len(chunks)} chunk(s) created.")

    # Return the list of file paths to the generated audio chunks for downstream processing
    return chunks