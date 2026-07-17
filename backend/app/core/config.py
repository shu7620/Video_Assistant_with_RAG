# import os
# from pymongo import MongoClient
# from dotenv import load_dotenv

# from langchain_mistralai import ChatMistralAI
# from langchain_groq import ChatGroq
# from langchain_openai import ChatOpenAI

# load_dotenv()

# class Settings:
#     # CORS Configuration Parameters
#     ALLOWED_ORIGINS: list = [
#         origin.strip() 
#         for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
#     ]
    
#     # Database Configurations
#     MONGO_URI: str = os.getenv("MONGO_URI")
#     DB_NAME: str = "video_assistant_db"
#     VECTORS_COLLECTION: str = "vectors"
#     TASKS_COLLECTION: str = "tasks"

# settings = Settings()

# # --- CENTRALIZED DATABASE CONNECTION POOL ---
# # Opening a single global client creates an automated internal connection pool.
# # This prevents exhausting your MongoDB cluster socket limits during high usage.

# mongo_client = MongoClient(settings.MONGO_URI, maxPoolSize=50, minPoolSize=10)
# db = mongo_client[settings.DB_NAME]



# # 1. Primary Engine: Mistral AI
# Shared_llm = ChatMistralAI(
#     model="mistral-small-latest",
#     mistral_api_key=os.getenv("MISTRAL_API_KEY"),
#     temperature=0.3,
#     max_retries=5,
#     timeout=60.0
# )

# # 2. First Fallback Engine: Groq (Blazing fast processing speed)
# Groq_llm = ChatGroq(
#     model="llama-3.3-70b-versatile",
#     groq_api_key=os.getenv("GROQ_API_KEY"),
#     temperature=0.3,
#     max_retries=3,
#     timeout=60.0
# )

# # 3. Final Fallback Engine: OpenRouter (Universal Redundancy Routing Layer)
# OpenRouter_llm = ChatOpenAI(
#     model="google/gemini-2.5-flash",
#     openai_api_key=os.getenv("OPENROUTER_API_KEY"),
#     openai_api_base="https://openrouter.ai/api/v1",
#     temperature=0.3,
#     max_retries=3,
#     timeout=60.0
# )

# Correction_llm = ChatMistralAI(
#     model="mistral-small-latest",
#     mistral_api_key=os.getenv("MISTRAL_API_KEY"),
#     temperature=0.0,
#     max_retries=3,
#     timeout=30.0
# )

import os
from pymongo import MongoClient
from dotenv import load_dotenv
import boto3

from langchain_mistralai import ChatMistralAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv()

class Settings:
    # CORS Configuration Parameters
    ALLOWED_ORIGINS: list = [
        origin.strip() 
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    ]
    
    # Database Configurations
    MONGO_URI: str = os.getenv("MONGO_URI")
    DB_NAME: str = "video_assistant_db"
    VECTORS_COLLECTION: str = "vectors"
    TASKS_COLLECTION: str = "tasks"

    # AWS S3 Cloud Storage Configurations
    AWS_STORAGE_BUCKET_NAME: str = os.getenv("AWS_STORAGE_BUCKET_NAME", "transcribex-media-storage-prod")
    AWS_DEFAULT_REGION: str = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2")

settings = Settings()

# --- CENTRALIZED DATABASE CONNECTION POOL ---
mongo_client = MongoClient(settings.MONGO_URI, maxPoolSize=50, minPoolSize=10)
db = mongo_client[settings.DB_NAME]

# --- AWS S3 GLOBAL CLIENT CONNECTION ---
# Leverages EC2 IAM Instance Profile role automatically if environment keys are empty
s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_DEFAULT_REGION
)

# 1. Primary Engine: Mistral AI
Shared_llm = ChatMistralAI(
    model="mistral-small-latest",
    mistral_api_key=os.getenv("MISTRAL_API_KEY"),
    temperature=0.3,
    max_retries=5,
    timeout=60.0
)

# 2. First Fallback Engine: Groq
Groq_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.3,
    max_retries=3,
    timeout=60.0
)

# 3. Final Fallback Engine: OpenRouter
OpenRouter_llm = ChatOpenAI(
    model="google/gemini-2.5-flash",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.3,
    max_retries=3,
    timeout=60.0
)

Correction_llm = ChatMistralAI(
    model="mistral-small-latest",
    mistral_api_key=os.getenv("MISTRAL_API_KEY"),
    temperature=0.0,
    max_retries=3,
    timeout=30.0
)