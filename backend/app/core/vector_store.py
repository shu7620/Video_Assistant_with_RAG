import os
from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.config import db, settings
from dotenv import load_dotenv
load_dotenv()


ATLAS_INDEX_NAME = "vector_index"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
GLOBAL_EMBEDDINGS = None

def load_embedding():
    """
    Implements a thread-safe Lazy Initialization Singleton pattern.
    The HuggingFace model will ONLY load into RAM when this function 
    is explicitly called, and exactly once.
    """
    global GLOBAL_EMBEDDINGS
    
    if GLOBAL_EMBEDDINGS is None:
        print("📥 Loading HuggingFace Embedding Model into memory for the first time...")
        GLOBAL_EMBEDDINGS = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    else:
        print("🔄 Reusing already cached global embedding model instance.")
        
    return GLOBAL_EMBEDDINGS




def format_seconds_to_timestamp(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def build_vector_store(timestamped_segments: list, task_id: str) -> MongoDBAtlasVectorSearch:
    """Groups consecutive text segments and streams them directly to your MongoDB Atlas Cloud Instance."""
   
    docs = []
    
    current_chunk_text = ""
    current_start_time = None
    max_chunk_chars = 500
    
    for i, segment in enumerate(timestamped_segments):
        text = segment["text"].strip()
        if not text:
            continue
            
        if current_start_time is None:
            current_start_time = segment["start"]
            
        current_chunk_text += " " + text
        
        if len(current_chunk_text) >= max_chunk_chars or i == len(timestamped_segments) - 1:
            end_time = segment["end"]
            
            metadata = {
                "analysis_id": task_id,
                "chunk_index": len(docs),
                "start_seconds": float(current_start_time),
                "end_seconds": float(end_time),
                "timestamp_label": f"[{format_seconds_to_timestamp(current_start_time)}]"
            }
            
            docs.append(Document(page_content=current_chunk_text.strip(), metadata=metadata))
            current_chunk_text = ""
            current_start_time = None

    if not docs:
       
        return None

    
    collection = db[settings.VECTORS_COLLECTION]

    vector_store = MongoDBAtlasVectorSearch.from_documents(
        documents=docs,
        embedding=load_embedding(),
        collection=collection,
        index_name=ATLAS_INDEX_NAME
    )
    return vector_store

def load_vector_store():
    """Loads the vector search wrapper and exposes the raw collection for native aggregations."""
    
    collection = db[settings.VECTORS_COLLECTION]
    
    # We initialize the wrapper to keep compatibility for other modules
    vector_search_wrapper = MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=load_embedding(),
        index_name=ATLAS_INDEX_NAME,
        text_key="text",
        embedding_key="embedding"
    )
    
    # Return a tuple: (wrapper, raw_pymongo_collection)
    return vector_search_wrapper, collection
