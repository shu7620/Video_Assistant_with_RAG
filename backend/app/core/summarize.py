from langchain_mistralai import ChatMistralAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os

Shared_llm= ChatMistralAI(model="mistral-small-latest",mistral_api_key=os.getenv("MISTRAL_API_KEY"),temperature=0.3,max_retries=5)


def split_transcript(transcript:str)->list:
    
    splitter=RecursiveCharacterTextSplitter(chunk_size=3000,chunk_overlap=200)
    return splitter.split_text(transcript)

def summarize_transcript(transcript:str)->str:
    
    map_prompt=ChatPromptTemplate.from_messages(
        [
            ("system","You are a helpful assistant that summarizes video transcripts concisely."),
            ("human","Summarize the following transcript:\n\n{transcript}")
        ]
    )
    
    map_chain=map_prompt|Shared_llm|StrOutputParser()
    
    chunks=split_transcript(transcript)
    
    batch_inputs=[{"transcript":chunk} for chunk in chunks]
    
    chunk_summaries=map_chain.batch(batch_inputs,config={"max_concurrency": 2})
    
    combined="\n\n".join(chunk_summaries)
    
    combined_prompt=ChatPromptTemplate.from_messages(
        [
            ('system',"You are a helpful assistant that takes multiple summaries of video transcript chunks and combines them into a single, concise summary."),
            ('human','Combine the following summaries into one concise summary:\n\n{combined}')
        ]
    )
    
    combined_chain=combined_prompt| Shared_llm|StrOutputParser()
    
    return combined_chain.invoke({"combined":combined})


def generate_title(transcript:str)->str:
    
    title_prompt=ChatPromptTemplate.from_messages(
        [
            ('system',"You are a helpful assistant that generates a concise and catchy title for a video based on its transcript."
             "The title should be of max 8-10 words. Return only the title, nothing else."),
            ('human','Generate a concise and catchy title for a video with the following transcript:\n\n{transcript}')
        ]     
    )
    
    title_chain=title_prompt|Shared_llm|StrOutputParser()
    
    return title_chain.invoke({"transcript": transcript[:2000]})