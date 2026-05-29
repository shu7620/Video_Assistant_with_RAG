import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_mistralai import ChatMistralAI
import os
from dotenv import load_dotenv
load_dotenv()


# set temperature to 0 as we want determistic output
Correction_llm= ChatMistralAI(model="mistral-small-latest",mistral_api_key=os.getenv("MISTRAL_API_KEY"),temperature=0.0,max_retries=3)

def basic_text_cleaner(text:str)->str:
    """Uses regex and rules to remove conversational fluff, extra spaces, and symbols."""
    
    # 1. convert to lowercase
    text=text.lower().strip()
    
    # 2. remove common conversational greetings/fillers at the start of query
    fillers=[ 
        r"^hey\b", r"^hi\b", r"^hello\b", r"^please\b", r"^can you\b", 
        r"^tell me\b", r"^find information about\b", r"^search for\b",
        r"^help me\b", r"^provide information\b", r"^look for\b"
    ]
    
    for pattern in fillers:
        text=re.sub(pattern,"",text).strip()
        
    # 3. clean up leading punctuation hooks left behind by fillers(like commas etc)
    text=re.sub(r"^[,\s?]+","",text).strip()
    
    # collapse any internal double space or triple space to a single space
    text = re.sub(r"\s+", " ", text)
    
    return text

def llm_query_normalizer(raw_query:str)->str:
    """Uses a structural prompt loop to correct spelling mistakes, typos, and expand abbreviations."""
    
    # Run the regex rule pass first
    cleaned_query=basic_text_cleaner(raw_query)

    # If user query is exponentially short or wmpty afetr basic cleaning then return raw query
    if len(cleaned_query)<3:
        return raw_query
    
    # Structural prompt instructing the LLM to output ONLY the optimized query
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a query refinement assistant for an AI Meeting Assistant application. 
Your single job is to fix spelling mistakes, typos, grammatical errors, and expand common corporate/tech shorthand shorthand (e.g., convert 'action items' to 'action items', 'db' to 'database', 'mgmt' to 'management') found in the search query.

CRITICAL RULES:
1. Fix all typos and misspellings.
2. Maintain the core meaning and search intent of the user.
3. Return ONLY the final corrected query text. Do not add any conversational introductions, explanations, quotes, or punctuation markers around it.

Examples:
Input: "what was desided about the db mgmt?"
Output: "what was decided about the database management"

Input: "extract actionitmes for vivek"
Output: "action items for vivek"
"""
        ),
        ("human", "{query}")
    ])
    
    normalization_chain=prompt|Correction_llm|StrOutputParser()
    
    try:
        normalized_query=normalization_chain.invoke({'query':cleaned_query})
        print(f"🔮 Query Normalizer: '{raw_query}' → '{normalized_query.strip()}'")
        return normalized_query.strip()
    except Exception as e:
        # Fallback safety: If the LLM network call fails, don't crash the app, use the rule-cleaned query
        print(f"⚠️ Query Normalizer failed: {str(e)}. Falling back to base text.")
        return cleaned_query if cleaned_query else raw_query
    

    
    