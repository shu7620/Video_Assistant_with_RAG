import os
from langchain_mistralai import ChatMistralAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda,RunnablePassthrough
from core.vector_store import build_vector_store,load_vector_store,get_retriever
from core.normalizer import llm_query_normalizer
from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_community.document_compressors import FlashrankRerank
from dotenv import load_dotenv
load_dotenv()

Shared_llm= ChatMistralAI(model="mistral-small-latest",mistral_api_key=os.getenv("MISTRAL_API_KEY"),temperature=0.3,max_retries=5)

# def format_docs(docs):
#     return "\n\n".join([doc.page_content for doc in docs])

def format_docs(docs):
    formatted_chunks = []
    for doc in docs:
        timestamp = doc.metadata.get("timestamp_label", "[00:00]")
        # Prepend the timestamp label to the chunk text for the LLM context wrapper
        formatted_chunks.append(f"{timestamp} {doc.page_content}")
    return "\n\n".join(formatted_chunks)



def create_rag_chain_from_retriever(retriever):
    prompt = ChatPromptTemplate.from_messages(

        [(
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
       ]
       )
     
    rag_chain=(
        {
            "context": retriever |RunnableLambda(format_docs),
            "question":RunnablePassthrough()
        }
        |prompt
        |Shared_llm
        |StrOutputParser()
    )
    
    return rag_chain




# Change ONLY this signature inside your rag_engine.py:
def build_rag_chain(timestamped_segments: list, persist_dir: str):
    # Pass down the raw structured list rather than a transcript string
    vector_store = build_vector_store(timestamped_segments, persist_dir=persist_dir)
    
    
    # 1. Expand the initial retrieval window (k=15 instead of 4)
    # This allows Chroma to fetch a wider net of potentially relevant context.
    base_retriever = get_retriever(vector_store, k=15)
    
    # 2. Instantiate the Free, Local FlashRank Compressor Engine
    # It uses 'ms-marco-MiniLM-L-6-v2' by default—lightweight, free, and highly accurate.
    compressor = FlashrankRerank(top_n=4) # Reranks and selects only the absolute top 4 results
    
    # 3. Construct the Reranking Contextual Compression Retriever
    reranking_retriever = ContextualCompressionRetriever(
        base_compressor=compressor, 
        base_retriever=base_retriever
    )
    
    return create_rag_chain_from_retriever(reranking_retriever)


def load_rag_chain(persist_dir:str):
    """
    Loads the Chroma vector store, hooks it into a wide-net retriever,
    and applies a FlashRank Contextual Compression filter to extract the best matches.
    """
    vector_store=load_vector_store(persist_dir=persist_dir)
    
    # 1. Expand the initial retrieval window (k=15 instead of 4)
    # This allows Chroma to fetch a wider net of potentially relevant context.
    base_retriever = get_retriever(vector_store, k=15)
    
    # 2. Instantiate the Free, Local FlashRank Compressor Engine
    # It uses 'ms-marco-MiniLM-L-6-v2' by default—lightweight, free, and highly accurate.
    compressor = FlashrankRerank(top_n=4) # Reranks and selects only the absolute top 4 results
    
    # 3. Construct the Reranking Contextual Compression Retriever
    reranking_retriever = ContextualCompressionRetriever(
        base_compressor=compressor, 
        base_retriever=base_retriever
    )
    
    return create_rag_chain_from_retriever(reranking_retriever)



def ask_question(rag_chain, question: str) -> str:
    print(f"Raw Question : {question}")
    # Query Normalizer
    normalized_question=llm_query_normalizer(question)
    
    print(f"Executing Optimized Query: {normalized_question}")
    
    answer = rag_chain.invoke(normalized_question)
    print(f"answer :{answer}")
    return answer