import os
from dotenv import load_dotenv
load_dotenv()

model=os.getenv("groq/llama-3.3-70b-versatile")
api_key= os.getenv("CHATGROQ_API_KEY")