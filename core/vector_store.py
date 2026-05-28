import os
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from dotenv import load_dotenv
load_dotenv()

CHROMA_DIR="vector_db"
COLLECTION_NAME="video_transcripts"
EMBEDDING_MODEL="all-MiniLM-L6-v2"


embeddings=HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
splitter=RecursiveCharacterTextSplitter(chunk_size=500,chunk_overlap=50)

def build_vector_store(transcript:str)->Chroma:
    print("Building Vector store...")
    
    chunks=splitter.split_text(transcript)
    
    docs=[
        Document(page_content=chunk,metadata={'chunk_index':i})
        for i,chunk in enumerate(chunks)
    ]
    vector_store=Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DIR
    )
    
    return vector_store

def load_vector_store()->Chroma:
    
    # Handle edge case where you try to load a database that hasn't been built yet
    if not os.path.exists(CHROMA_DIR):
        raise FileNotFoundError(
            f"The vector database directory '{CHROMA_DIR}' does not exist. "
            "Please call build_vector_store() first."
        )
        
    vector_store=Chroma(
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DIR
    )
    return vector_store
    
def get_retriever(vector_store:Chroma,top_k:int=4):
    return vector_store.as_retriever(
        search_type='similarity',
        search_kwargs={"k":top_k} 
    )