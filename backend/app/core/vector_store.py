import os
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
# from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv
load_dotenv()

CHROMA_DIR="vector_db"
COLLECTION_NAME="video_transcripts"
EMBEDDING_MODEL="all-MiniLM-L6-v2"

def load_embedding():
    embeddings=HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return embeddings
    
splitter=RecursiveCharacterTextSplitter(chunk_size=500,chunk_overlap=50)

def build_vector_store(transcript: str, persist_dir: str = CHROMA_DIR) -> Chroma:
    print(f"Building Vector store at {persist_dir}...")
    chunks = splitter.split_text(transcript)
    embeddings = load_embedding()
    
    docs = [
        Document(page_content=chunk, metadata={'chunk_index': i})
        for i, chunk in enumerate(chunks)
    ]
    vector_store = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=persist_dir # <--- Use the dynamic path passed
    )
    return vector_store

def load_vector_store(persist_dir: str = CHROMA_DIR) -> Chroma:
    if not os.path.exists(persist_dir): # <--- Check dynamic path
        raise FileNotFoundError(f"The vector database directory '{persist_dir}' does not exist.")
    embeddings = load_embedding()
    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=persist_dir # <--- Load dynamic path
    )
    return vector_store
    
def get_retriever(vector_store:Chroma,k:int=4):
    return vector_store.as_retriever(
        search_type='similarity',
        search_kwargs={"k":k} 
    )