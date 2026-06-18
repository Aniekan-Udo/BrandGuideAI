import asyncio
import httpx
from database import get_db_session, User
from jose import jwt
import os

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "brandguard_super_secret_jwt_key_2024")
ALGORITHM = "HS256"

async def test_stream():
    with get_db_session() as session:
        user = session.query(User).first()
        if not user:
            print("No users found.")
            return
        business_id = user.business_id
        
    token = jwt.encode({"sub": str(user.id)}, SECRET_KEY, algorithm=ALGORITHM)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "business_id": business_id,
        "content_type": "blog",
        "topic": "test topic for debugging stream",
        "format_type": "test format",
        "use_search": False
    }
    
    print("Hitting endpoint...")
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", "http://127.0.0.1:8000/conversation/generate/stream", headers=headers, json=payload) as response:
            print(f"Status: {response.status_code}")
            async for chunk in response.aiter_text():
                print(f"Chunk received: {repr(chunk)}")

asyncio.run(test_stream())
