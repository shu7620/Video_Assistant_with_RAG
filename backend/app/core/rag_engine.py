import os
from langchain_mistralai import ChatMistralAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda,RunnablePassthrough
from core.vector_store import build_vector_store,load_vector_store,get_retriever
from core.normalizer import llm_query_normalizer
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
            """You are an expert meeting assistant. Answer the user's question 
based ONLY on the meeting transcript context provided below.

Every chunk of context below starts with a timestamp label in brackets, like [MM:SS]. 
Whenever you provide information or answer a question, you MUST explicitly mention the 
corresponding timestamp(s) at the start or end of your sentences so the user knows exactly 
when it happened in the video.

If the answer is not found in the context, say: 
"I could not find this information in the meeting transcript."

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcript:
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



# def build_rag_chain(transcript:str,persist_dir:str):
#     vector_store=build_vector_store(transcript,persist_dir=persist_dir)
    
#     retriever=get_retriever(vector_store,k=4)
#     return create_rag_chain_from_retriever(retriever)


# Change ONLY this signature inside your rag_engine.py:
def build_rag_chain(timestamped_segments: list, persist_dir: str):
    # Pass down the raw structured list rather than a transcript string
    vector_store = build_vector_store(timestamped_segments, persist_dir=persist_dir)
    retriever = get_retriever(vector_store, k=4)
    return create_rag_chain_from_retriever(retriever)


def load_rag_chain(persist_dir:str):
    vector_store=load_vector_store(persist_dir=persist_dir)
    
    retriever=get_retriever(vector_store,k=4)
    return create_rag_chain_from_retriever(retriever)



def ask_question(rag_chain, question: str) -> str:
    print(f"Raw Question : {question}")
    # Query Normalizer
    normalized_question=llm_query_normalizer(question)
    
    print(f"Executing Optimized Query: {normalized_question}")
    
    answer = rag_chain.invoke(normalized_question)
    print(f"answer :{answer}")
    return answer