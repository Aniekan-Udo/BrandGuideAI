import os
from dotenv import load_dotenv
load_dotenv()

model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
api_key = os.getenv("GROQ_API_KEY", "")