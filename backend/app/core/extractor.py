from langchain_mistralai import ChatMistralAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os

Shared_llm= ChatMistralAI(model="mistral-small-latest",mistral_api_key=os.getenv("MISTRAL_API_KEY"),temperature=0.3,max_retries=5)

def chunk_transcript(transcript:str)->list:
    """Splits a large transcript into smaller chunks."""
    splitter=RecursiveCharacterTextSplitter(chunk_size=3000,chunk_overlap=200)
    return splitter.split_text(transcript)


def process_large_transcript(transcript:str,task_type:str)->str:
    """
    Splits transcript into chunks, processes them in parallel using .batch(),
    and reduces the results into a final consolidated output.
    """
    
    # Define prompts based on what we are extracting
    prompts = {
        "action_items": {
            "map": "You are an expert meeting analyst. Extract all action items from this meeting excerpt. For each provide: Task, Owner, and Deadline (if mentioned). Format as a numbered list. If none found say 'No action items found'.",
            "reduce": "You are given a list of action items extracted from different parts of a meeting. Combine them into a single, clean, consolidated numbered list. Remove any duplicates."
        },
        "decisions": {
            "map": "You are an expert meeting analyst. Extract all key decisions made from this meeting excerpt. Format as a numbered list. If none found say 'No key decisions found.'.",
            "reduce": "You are given a list of decisions made across different parts of a meeting. Combine them into a single, beautifully organized numbered list. Remove duplicates."
        },
        "questions": {
            "map": "You are an expert meeting analyst. Extract all unresolved questions or topics needing follow-up from this meeting excerpt. Format as a numbered list. If none found say 'No open questions found.'.",
            "reduce": "You are given a list of unresolved questions from different parts of a meeting. Combine them into a single clean numbered list. Remove duplicates."
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
    combined_results="\n\n".join(valid_results)
    reduce_prompt=ChatPromptTemplate.from_messages(
        [
            ('system',selected_prompt["reduce"]),
            ('human', "{text}")
        ]
    )
    reduce_chain=reduce_prompt|Shared_llm|StrOutputParser()
    
    return reduce_chain.invoke({"text": combined_results})


    


def extract_action_items(transcript:str)->str:
    return process_large_transcript(transcript,"action_items")



def extract_key_decisions(transcript:str)->str:
    return process_large_transcript(transcript,"decisions")
    


def extract_questions(transcript: str) -> str:
    return process_large_transcript(transcript,"questions")