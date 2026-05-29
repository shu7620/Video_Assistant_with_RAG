import os
from langchain_mistralai import ChatMistralAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda,RunnablePassthrough
from core.vector_store import build_vector_store,load_vector_store,get_retriever
from dotenv import load_dotenv
load_dotenv()

Shared_llm= ChatMistralAI(model="mistral-small-latest",mistral_api_key=os.getenv("MISTRAL_API_KEY"),temperature=0.3,max_retries=5)

def format_docs(docs):
    return "\n\n".join([doc.page_content for doc in docs])



def create_rag_chain_from_retriever(retriever):
    prompt = ChatPromptTemplate.from_messages(

        [(
            "system",
            """You are an expert meeting assistant. Answer the user's question 
based ONLY on the meeting transcript context provided below.

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



def build_rag_chain(transcript:str,persist_dir:str):
    vector_store=build_vector_store(transcript,persist_dir=persist_dir)
    
    retriever=get_retriever(vector_store,k=4)
    return create_rag_chain_from_retriever(retriever)



def load_rag_chain(persist_dir:str):
    vector_store=load_vector_store(persist_dir=persist_dir)
    
    retriever=get_retriever(vector_store,k=4)
    return create_rag_chain_from_retriever(retriever)



def ask_question(rag_chain, question: str) -> str:
    print(f"Question : {question}")
    answer = rag_chain.invoke(question)
    print(f"answer :{answer}")
    return answer