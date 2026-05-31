import os
from pymongo import MongoClient
from dotenv import load_dotenv

from langchain_mistralai import ChatMistralAI

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

settings = Settings()

# --- CENTRALIZED DATABASE CONNECTION POOL ---
# Opening a single global client creates an automated internal connection pool.
# This prevents exhausting your MongoDB cluster socket limits during high usage.

mongo_client = MongoClient(settings.MONGO_URI, maxPoolSize=50, minPoolSize=10)
db = mongo_client[settings.DB_NAME]



# Centralized LLM Engine instances
Shared_llm = ChatMistralAI(
    model="mistral-small-latest",
    mistral_api_key=os.getenv("MISTRAL_API_KEY"),
    temperature=0.3,
    max_retries=5
)

Correction_llm = ChatMistralAI(
    model="mistral-small-latest",
    mistral_api_key=os.getenv("MISTRAL_API_KEY"),
    temperature=0.0,
    max_retries=3
)