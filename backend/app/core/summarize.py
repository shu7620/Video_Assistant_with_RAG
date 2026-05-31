from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.config import Shared_llm
import os

import time
import logging

logger = logging.getLogger(__name__)




def rate_limit_safe_llm(max_retries: int = 5, initial_delay: int = 15, backoff_factor: int = 2):
    """
    A decorator to safeguard synchronous LangChain/LLM invocations 
    against HTTP 429 Rate Limits using exponential backoff.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).lower()
                    if "429" in error_msg or "rate limit" in error_msg or "rate_limited" in error_msg:
                        logger.warning(
                            f"⚠️ Mistral AI Ingestion Rate Limit Hit (HTTP 429) during execution of '{func.__name__}'. "
                            f"⏳ Cooling down: Sleeping for {delay} seconds before retry (Attempt {attempt + 1}/{max_retries})..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor  # Exponentially increase wait window bounds
                        continue
                    else:
                        raise e  # Fail immediately on non-rate-limit errors
            raise RuntimeError(f"❌ '{func.__name__}' exhausted all {max_retries} rate limit recovery windows.")
        return wrapper
    return decorator




def split_transcript(transcript:str)->list:
    
    splitter=RecursiveCharacterTextSplitter(chunk_size=3000,chunk_overlap=200)
    return splitter.split_text(transcript)

@rate_limit_safe_llm(max_retries=5, initial_delay=15)
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


@rate_limit_safe_llm(max_retries=5, initial_delay=15)
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
