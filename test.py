from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.summarize import summarize_transcript, generate_title
from core.extractor import extract_action_items,extract_key_decisions,extract_questions 
from dotenv import load_dotenv
load_dotenv()

source="https://www.youtube.com/watch?v=g9JIUM0MHgQ&t=2s"

chunks=process_input(source)
language='english'

# step 1; Transcribe the video
print("*"*50)
print("Entire Audio Transcript:\n\n")
print("*"*50)
transcript=transcribe_all(chunks, language=language)
print(transcript)

# step 2: Summarize the video

print("\n\n"+"*"*50)
print("Video Summary:\n\n")
print("*"*50)
summary=summarize_transcript(transcript)
print(summary)

print("*"*50)
print("Summary Title:\n\n")
print("*"*50)
title=generate_title(transcript)
print(title)

# step 3: Extract key points from video

print("*"*50)
print("Key Action Items:\n\n")
print("*"*50)
action_items=extract_action_items(transcript)
print(action_items)

print("*"*50)
print("Key Decisions:\n\n")
print("*"*50)
key_decisions=extract_key_decisions(transcript)
print(key_decisions)

print("*"*50)
print("Key Questions:\n\n")
print("*"*50)
questions=extract_questions(transcript)
print(questions)
