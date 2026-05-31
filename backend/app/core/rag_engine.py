import os
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from app.core.vector_store import build_vector_store, load_vector_store,load_embedding
from langchain_core.documents import Document
from app.core.normalizer import llm_query_normalizer
# from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain.retrievers import ContextualCompressionRetriever
from langchain_community.document_compressors import FlashrankRerank
from app.core.config import Shared_llm
import time
from dotenv import load_dotenv
load_dotenv()



def format_docs(docs):
    """Formats retrieved LangChain Document segments into strings with timestamp markers."""
    formatted_chunks = []
    
    
    for doc in docs:
        timestamp = doc.metadata.get("timestamp_label", "[00:00]")
        formatted_chunks.append(f"{timestamp} {doc.page_content}")
        
    
    return "\n\n".join(formatted_chunks)


def create_native_mongodb_retriever(task_id: str):
    """
    Creates a native MongoDB MQL pipeline execution function 
    wrapped tightly as a LangChain runnable component.
    """
    # Load the global cached embedding model and the native PyMongo connection link
    embeddings_model = load_embedding()
    _, collection = load_vector_store()

    def retrieve_context_from_mongo(query: str) -> list:
        # 1. Vectorize the text query into a 384-dimensional array string
        query_embedding = embeddings_model.embed_query(query)
        
        # 2. Build the aggregate pipeline using the exact code pattern you suggested
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",      # Must match your Atlas Search index name exactly
                    "path": "embedding",         # Target the flat embedded array key
                    "queryVector": query_embedding,
                    "numCandidates": 150,
                    "limit": 10,                 # Pull top 10 potential matches
                    # FILTER: Restricts search space to this video before vector matching
                    "filter": {
                        "analysis_id": task_id
                    }
                }
            }
        ]
        
        # 3. Execute query on MongoDB Cloud Cluster
        cursor_results = collection.aggregate(pipeline)
        
        # 4. Map raw documents into LangChain format so the downstream LLM prompts understand them
        langchain_documents = []
        for doc in cursor_results:
            # Reconstruct standard Document format maps dynamically
            langchain_documents.append(
                Document(
                    page_content=doc.get("text", ""),
                    metadata={
                        "analysis_id": doc.get("analysis_id"),
                        "timestamp_label": doc.get("timestamp_label", "[00:00]"),
                        "chunk_index": doc.get("chunk_index")
                    }
                )
            )
        return langchain_documents

    return RunnableLambda(retrieve_context_from_mongo)


def create_rag_chain_from_retriever(retriever_runnable):
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are an expert video analyser. Your task is to answer the user's question by prioritizing the provided video transcript context.

Follow these strict guidelines depending on where the information comes from:

1. IF THE ANSWER IS IN THE VIDEO TRANSCRIPT CONTEXT:
   - Answer the question precisely using the context.
   - Every chunk of context starts with a timestamp label in brackets like [MM:SS]. You MUST explicitly mention the corresponding timestamp(s) at the start or end of your sentences so the user knows exactly when it happened in the video.
   - If quoting someone from the video, mention their name clearly.

2. IF THE ANSWER IS NOT FOUND IN THE CONTEXT:
   - Start your response by explicitly stating: "I could not find this specific information in the video transcript."
   - Then, provide a brief, helpful answer to the question using your own general knowledge.
   - You MUST add a disclaimer label exactly like this at the end of your general knowledge response: "[Source: Assistant General Knowledge]".

Always be concise, professional, and clear about the source of your information.

Context from video transcript:
{context}""",
        ),
        ("human", "{question}"),
    ])
     
    rag_chain = (
        {
            "context": retriever_runnable | RunnableLambda(format_docs),
            "question": RunnablePassthrough()
        }
        | prompt
        | Shared_llm
        | StrOutputParser()
    )
    return rag_chain

def build_rag_chain(task_id: str):
    # Pass down the raw structured list rather than a transcript string
    
    
    
    # Pre-filter limits search space strictly to documents matching this analysis_id
    base_retriever = create_native_mongodb_retriever(task_id)
    
    compressor = FlashrankRerank(top_n=4)
    reranking_retriever = ContextualCompressionRetriever(
        base_compressor=compressor, 
        base_retriever=base_retriever
    )
    
    return create_rag_chain_from_retriever(reranking_retriever)


def load_rag_chain(task_id: str):
    """Loads the MongoDB vector store, hooks it into a wide-net pre-filtered retriever, and applies FlashRank."""
    
    
    
    # Pre-filter limits search space strictly to documents matching this analysis_id
    base_retriever = create_native_mongodb_retriever(task_id)
    
    compressor = FlashrankRerank(top_n=4)
    reranking_retriever = ContextualCompressionRetriever(
        base_compressor=compressor, 
        base_retriever=base_retriever
    )
    
    return create_rag_chain_from_retriever(reranking_retriever)




def ask_question(rag_chain, question: str) -> str:
    """
    Normalizes the incoming prompt query and executes it synchronously.
    Implements a robust backoff cooling window to handle Mistral free-tier 
    rate limits (HTTP 429) gracefully without streaming.
    """
    
    # Query Normalizer
    normalized_question = llm_query_normalizer(question)
    
    
    # --- RATE LIMIT RETRY CONFIGURATION ---
    max_retries = 5       # Maximum number of retry attempts before giving up
    initial_delay = 8     # Starting pause window in seconds (gives Mistral TPM time to reset)
    backoff_factor = 2    # Multiplier to double the wait time on successive hits

    for attempt in range(max_retries):
        try:
            # Execute standard synchronous invocation pass
            answer = rag_chain.invoke(normalized_question)
            
            return answer
            
        except Exception as e:
            error_str = str(e).lower()
            # Inspect if the error is related to a 429 status code or a rate limit exception
            if "429" in error_str or "rate limit" in error_str or "rate_limited" in error_str:
                wait_time = initial_delay * (backoff_factor ** attempt)
                
                time.sleep(wait_time)
                continue
            else:
                # If it's any other error profile, raise it immediately to avoid endless looping
                raise e
    else:
        # Executes only if all retry attempts are exhausted
        error_msg = "❌ Failed to generate response via Mistral AI after multiple rate-limit retries. Please wait a moment and try again."
        return error_msg
