import os
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv
load_dotenv()

CHROMA_DIR = "vector_db"
COLLECTION_NAME = "video_transcripts"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

def load_embedding():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

def format_seconds_to_timestamp(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def build_vector_store(timestamped_segments: list, persist_dir: str = CHROMA_DIR) -> Chroma:
    """
    Groups small consecutive segments together up to a character limit 
    so the embedding model has enough contextual data to perform accurate similarity searches.
    """
    print(f"Building Timestamped Vector store at {persist_dir}...")
    embeddings = load_embedding()
    docs = []
    
    current_chunk_text = ""
    current_start_time = None
    max_chunk_chars = 500  # Safe semantic size matching your original setup
    
    for i, segment in enumerate(timestamped_segments):
        text = segment["text"].strip()
        if not text:
            continue
            
        if current_start_time is None:
            current_start_time = segment["start"]
            
        current_chunk_text += " " + text
        
        # Once the text accumulation crosses our character size boundary, or it's the last element
        if len(current_chunk_text) >= max_chunk_chars or i == len(timestamped_segments) - 1:
            end_time = segment["end"]
            
            metadata = {
                "chunk_index": len(docs),
                "start_seconds": float(current_start_time),
                "end_seconds": float(end_time),
                "timestamp_label": f"[{format_seconds_to_timestamp(current_start_time)}]"
            }
            
            # Save the clean accumulated paragraph so similarity embeddings work perfectly!
            docs.append(Document(page_content=current_chunk_text.strip(), metadata=metadata))
            
            # Reset buffers for the next block group
            current_chunk_text = ""
            current_start_time = None

    if not docs:
        print("⚠️ Warning: No valid documents were generated for the vector store.")
        return None

    vector_store = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=persist_dir
    )
    return vector_store

def load_vector_store(persist_dir: str = CHROMA_DIR) -> Chroma:
    if not os.path.exists(persist_dir):
        raise FileNotFoundError(f"The vector database directory '{persist_dir}' does not exist.")
    embeddings = load_embedding()
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=persist_dir
    )
    
def get_retriever(vector_store: Chroma, k: int = 4):
    return vector_store.as_retriever(
        search_type='similarity',
        search_kwargs={"k": k} 
    )