import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
import redis
from model import LLMSingleton
from limiter import limiter, RateLimitExceeded
from fastapi.responses import JSONResponse
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from database import engine, init_db
    required = ["GROQ_API_KEY", "POSTGRES_URI", "REDIS_URL", "TAVILY_API_KEY"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {missing}")
    app.state.db_engine = engine
    init_db()
    app.state.llm = LLMSingleton().get()
    app.state.redis = redis.Redis(host="redis", port=6379, decode_responses=True, socket_timeout=10, socket_connect_timeout=10)
    logger.info("BrandGuard AI started successfully")
    yield
    engine.dispose()
    logger.info("Shutting down BrandGuard AI...")


app = FastAPI(
    title="BrandGuard AI",
    description="Brand voice content generation API",
    version="1.0.0",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://brandguard.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})
from routers import users, conversation, document
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(conversation.router, prefix="/conversation", tags=["Conversation"])
app.include_router(document.router, prefix="/documents", tags=["Documents"])
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
