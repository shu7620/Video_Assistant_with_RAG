from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
import time
import logging
import json
from core.config import Shared_llm

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



def chunk_transcript(transcript:str)->list:
    """Splits a large transcript into smaller chunks."""
    splitter=RecursiveCharacterTextSplitter(chunk_size=3000,chunk_overlap=200)
    return splitter.split_text(transcript)


def process_large_transcript(transcript:str,task_type:str)->list:
    """
    Splits transcript into chunks, processes them in parallel using .batch(),
    and reduces the results into a final consolidated output.
    """
    
    # Define prompts based on what we are extracting
    prompts = {
        "action_items": {
            "map": "You are an expert meeting analyst. Extract all action items from this meeting excerpt. For each provide: Task, Owner, and Deadline (if mentioned). Format as a clear text bullet point. If none found say 'No action items found'.",
            "reduce": "You are given raw action items extracted from different parts of a meeting. Combine them into a single, clean JSON array of strings representing the unique tasks. Return ONLY valid JSON. Example: [\"Task 1\", \"Task 2\"]"
        },
        "decisions": {
            "map": "You are an expert meeting analyst. Extract all key decisions made from this meeting excerpt. Format as a clear text bullet point. If none found say 'No key decisions found.'.",
            "reduce": "You are given raw decisions made across different parts of a meeting. Combine them into a single, clean JSON array of strings representing unique core decisions. Return ONLY valid JSON. Example: [\"Decision 1\", \"Decision 2\"]"
        },
        "questions": {
            "map": "You are an expert meeting analyst. Extract all unresolved questions or topics needing follow-up from this meeting excerpt. Format as a clear text bullet point. If none found say 'No open questions found.'.",
            "reduce": "You are given raw unresolved questions from different parts of a meeting. Combine them into a single, clean JSON array of strings representing unique questions. Return ONLY valid JSON. Example: [\"Question 1\", \"Question 2\"]"
        }
    }
    
    selected_prompt=prompts[task_type]
    chunks=chunk_transcript(transcript)
    
    # ---- STEP 1: MAP (Parallel Processing) ----
    map_prompt=ChatPromptTemplate.from_messages(
        [
            ('system',selected_prompt["map"]),
            ('human', "{text}")
        ]
    )
    map_chain=map_prompt|Shared_llm|StrOutputParser()
    
    # .batch() automatically sends all chunks to Mistral in parallel
    batch_inputs=[{"text":chunk} for chunk in chunks]
    chunk_results=map_chain.batch(batch_inputs,config={"max_concurrency": 2})
    
    # ---- NEW: FILTER STEP ----
    # Remove the placeholder strings so they don't pollute the final reduce step
    fallbacks = {"No action items found", "No key decisions found.", "No open questions found."}
    valid_results = [res for res in chunk_results if res.strip() not in fallbacks]
    
    # If absolutely nothing was found across ALL chunks, we can stop early!
    if not valid_results:
        # Returns the appropriate "No items found" message depending on the task
        if task_type == "action_items": return "No action items found."
        if task_type == "decisions": return "No key decisions found."
        return "No open questions found."
    
    # ---- STEP 2: REDUCE (Consolidate Results) ----
    combined_results = "\n\n".join(valid_results)
    reduce_prompt = ChatPromptTemplate.from_messages([
        ('system', selected_prompt["reduce"]),
        ('human', "{text}")
    ])
    
    reduce_chain = reduce_prompt | Shared_llm | StrOutputParser()
    
    raw_json_output = reduce_chain.invoke({"text": combined_results})
    
    try:
        # Clean up any markdown code blocks the LLM might have wrapped the JSON in
        cleaned_json_string = raw_json_output.replace("```json", "").replace("```", "").strip()
        parsed_list = json.loads(cleaned_json_string)
        if isinstance(parsed_list, list):
            return [str(item).strip() for item in parsed_list if str(item).strip()]
        return [raw_json_output.strip()]
    except Exception as e:
        logger.error(f"Failed parsing Map-Reduce JSON array string: {str(e)}. Falling back to split array.")
        return [line.strip("- ") for line in raw_json_output.split("\n") if line.strip()]


    

@rate_limit_safe_llm(max_retries=5, initial_delay=15)
def extract_action_items(transcript:str)->str:
    return process_large_transcript(transcript,"action_items")


@rate_limit_safe_llm(max_retries=5, initial_delay=15)
def extract_key_decisions(transcript:str)->str:
    return process_large_transcript(transcript,"decisions")
    

@rate_limit_safe_llm(max_retries=5, initial_delay=15)
def extract_questions(transcript: str) -> str:
    return process_large_transcript(transcript,"questions")