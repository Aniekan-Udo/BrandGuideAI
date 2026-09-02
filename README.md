# BrandMuse AI

## Project Summary

BrandMuse AI is a content generation platform that learns a company's unique brand voice from uploaded documents and then produces new marketing content that sounds like the company wrote it. Instead of relying on generic AI writing, BrandMuse analyzes tone, language patterns, structural habits, and signature phrases from real company materials (blog posts, ad copy, social media, proposals, etc.) and enforces those patterns in every piece of content it generates.

The system is designed for marketing teams who need to scale content production without sacrificing brand consistency. A user uploads their existing brand documents, the system extracts and synthesizes their brand identity into a "Brand Brain," and then uses that knowledge to generate, review, and refine new content -- all before a human ever sees it.

**The core value proposition:** content that is on-brand by default, not by accident.

---

## How It Works

BrandMuse uses a multi-agent pipeline where each agent has a single responsibility. Content passes through four stages before it reaches the user:

1. **Researcher** -- Gathers context for the requested topic. By default, it retrieves relevant passages from the company's own uploaded documents using a vector search (RAG). Optionally, it can also search the web for current trends, statistics, or industry data.

2. **Writer** -- Generates the content draft. The writer receives the research context, the synthesized Brand Brain (tone rules, vocabulary, structural patterns), and any historical feedback patterns from previous human reviews. If the content is being revised after enforcement feedback, the writer incorporates the enforcer's specific critique.

3. **Enforcer** -- Scores the draft against the brand profile across four dimensions: style match, tone match, structure match, and signature phrase match. It also runs a hallucination check to ensure no fabricated claims, statistics, or client references appear in the output. If the score is below the approval threshold, the content is sent back to the writer with actionable feedback. This loop can repeat until the content meets the quality bar.

4. **Deployer** -- Persists the approved content to the database, saves it to the learning memory for future pattern analysis, and optionally sends a webhook notification. High-scoring content is automatically promoted back into the brand metrics system so the Brand Brain improves over time.

---

## Architecture Overview

```
                          +------------------+
                          |   FastAPI (API)   |
                          +--------+---------+
                                   |
                          +--------v---------+
                          |   RabbitMQ        |
                          |   (Task Queue)    |
                          +--------+---------+
                                   |
               +-------------------+-------------------+
               |                   |                   |
    +----------v------+  +--------v-------+  +--------v--------+
    | Generation       |  | Feedback       |  | RAG / Metrics    |
    | Workers (x2)     |  | Worker         |  | Workers          |
    +----------+------+  +--------+-------+  +--------+--------+
               |                   |                   |
               +-------------------+-------------------+
                                   |
                     +-------------+-------------+
                     |                           |
              +------v------+            +-------v------+
              | PostgreSQL   |            | Redis        |
              | + pgvector   |            | (Cache +     |
              |              |            |  Streaming)  |
              +--------------+            +--------------+
```

### Technology Stack

| Layer             | Technology                                    | Purpose                                          |
|-------------------|-----------------------------------------------|--------------------------------------------------|
| API Framework     | FastAPI                                       | REST API with async support and dependency injection |
| Agent Orchestration | LangGraph                                   | Stateful multi-agent pipeline with conditional routing |
| LLM Providers     | Google Gemini (primary), Groq (fallback)     | Content generation, metrics extraction, scoring  |
| Vector Search     | LlamaIndex + pgvector                        | Retrieval-augmented generation from brand documents |
| Embeddings        | FastEmbed (BAAI/bge-small-en-v1.5)           | Lightweight, self-hosted document embeddings     |
| Task Queue        | Celery + RabbitMQ                             | Distributed async task processing                |
| Database          | PostgreSQL 16 with pgvector extension         | Persistent storage, vector similarity search     |
| Cache / Streaming | Redis                                         | Brand Brain caching, real-time generation streaming |
| Document Parsing  | PyMuPDF4LLM                                   | PDF to structured markdown conversion            |
| Auth              | JWT (python-jose) + Argon2 (pwdlib)           | Token-based authentication with secure hashing   |
| Frontend          | React + TypeScript + Vite                     | Single-page application                          |
| Deployment        | Docker Compose                                | Multi-container orchestration                    |

---

## Key Design Decisions and Tradeoffs

### 1. Multi-Agent Pipeline vs. Single-Prompt Generation

**Decision:** Content generation is split across four specialized agents (Researcher, Writer, Enforcer, Deployer) instead of using a single large prompt.

**Benefit:** Each agent can be independently tuned, tested, and improved. The enforcer can reject and loop back to the writer without re-running research. Each agent uses a different LLM temperature setting optimized for its task (low temperature for scoring, higher for creative writing).

**Tradeoff:** This adds latency. A single piece of content passes through multiple LLM calls rather than one. Total generation time is higher than a single-prompt approach, but content quality and brand consistency are significantly better.

---

### 2. Synthesized Brand Brain vs. Raw Document Retrieval

**Decision:** Instead of sending raw document chunks to the writer every time, the system pre-processes all uploaded documents into a single synthesized "Brand Brain" -- a structured profile covering tone, vocabulary, sentence patterns, structural habits, and brand assets.

**Benefit:** The writer receives a consistent, distilled representation of the brand rather than potentially contradictory or noisy document chunks. This also reduces per-generation token usage because the Brand Brain is cached and reused, rather than re-embedding and retrieving documents on every request.

**Tradeoff:** Synthesis adds an upfront processing cost when documents are uploaded. If the synthesis captures the wrong patterns (or misses important nuances), all subsequent content will inherit that bias. The mitigation is that new documents and high-scoring generations continuously update the Brand Brain, so it self-corrects over time.

---

### 3. Dual Retrieval (RAG + Brand Brain) vs. Single Source

**Decision:** The researcher fetches topic-relevant document chunks via vector search (RAG), while the writer and enforcer use the pre-synthesized Brand Brain for style guidance. Both systems draw from the same uploaded documents, but serve different purposes.

**Benefit:** RAG provides topic-specific factual grounding (product details, statistical claims), while the Brand Brain provides style and tone guidance. This separation prevents factual information from diluting style signals and vice versa.

**Tradeoff:** Maintaining two systems that draw from the same documents introduces complexity. The RAG index and the Brand Brain metrics can become stale at different rates if the cache invalidation or synthesis pipeline has issues.

---

### 4. Asynchronous (Celery) Content Generation vs. Synchronous API Calls

**Decision:** All content generation is dispatched to Celery workers and executed asynchronously. The API immediately returns a generation ID, and the client polls or streams results via Redis.

**Benefit:** The API remains responsive even under heavy load. Generation can take 30 seconds or more (multiple LLM calls per piece of content), and tying up an HTTP connection for that duration is impractical. Workers can be scaled horizontally by increasing replica counts.

**Tradeoff:** The client must handle polling logic and eventual consistency. The user does not receive content instantly on submission -- they must wait and check back. Real-time streaming over Redis partially mitigates this, but adds complexity to the frontend.

---

### 5. Dedicated Task Queues per Worker Type vs. Shared Queue

**Decision:** Celery tasks are routed to four separate queues (generation, feedback, retraining, rag_refresh) with dedicated worker pools for each.

**Benefit:** Generation jobs (which are CPU and latency intensive) cannot starve lightweight feedback or RAG refresh tasks. Each queue can be scaled independently -- you can run two generation workers and one feedback worker if generation is the bottleneck.

**Tradeoff:** This requires more memory and infrastructure overhead compared to a single shared queue. Each worker pool loads the full application, including the embedding model. On resource-constrained environments, this can be a significant cost.

---

### 6. Self-Hosted Embeddings (FastEmbed) vs. API-Based Embeddings

**Decision:** Document embeddings use the BAAI/bge-small-en-v1.5 model via FastEmbed, which runs locally inside the Docker container rather than calling an external embedding API.

**Benefit:** No per-request embedding cost, no external API dependency, and no data leaves the infrastructure. Embedding latency is low because the model is loaded into memory once at startup via a dedicated init container.

**Tradeoff:** The embedding model consumes GPU or CPU memory on every worker that needs it. The bge-small-en-v1.5 model is compact (384 dimensions), so quality is slightly below larger models like text-embedding-3-large. For most brand content use cases, this quality level is sufficient.

---

### 7. Human-in-the-Loop Feedback vs. Fully Autonomous Generation

**Decision:** The system supports both autonomous operation (content auto-approved if the enforcer score exceeds the threshold) and human review. When a user rejects content and provides feedback, the system automatically re-generates with the human feedback injected into the prompt.

**Benefit:** Humans remain in control of content quality. The feedback is stored and used for future pattern analysis, so the system learns what the humans approve and reject over time. High-scoring human-approved content is promoted back into the Brand Brain with elevated weight, creating a virtuous improvement cycle.

**Tradeoff:** Including human feedback in the loop introduces latency and requires the user to actively engage. If users do not provide feedback, the self-improvement mechanism stalls and the system relies entirely on its initial synthesis.

---

### 8. LLM Provider Routing (Gemini Primary, Groq Fallback) vs. Single Provider

**Decision:** The system supports multiple LLM backends (Gemini, Groq, OpenAI, Ollama) and routes different task types to different providers. Currently, all modes default to Gemini 2.5 Flash when a Google API key is available, falling back to Groq (Llama 3.3 70B) otherwise.

**Benefit:** Avoids vendor lock-in. If one provider has an outage or rate limit issue, the system can failover. Different providers can also be selected for cost optimization (cheaper models for structured JSON extraction, more capable models for creative writing).

**Tradeoff:** Supporting multiple providers adds code complexity in the model layer. Different providers have different tokenization, context windows, and output characteristics, which can cause subtle behavioral differences when switching between them.

---

## Environment Variables

The following environment variables must be configured in a `.env` file at the project root:

| Variable            | Required | Description                             |
|---------------------|----------|-----------------------------------------|
| `GROQ_API_KEY`      | Yes      | API key for Groq LLM provider           |
| `GOOGLE_API_KEY`    | Yes      | API key for Google Gemini                |
| `POSTGRES_URI`      | Yes      | PostgreSQL connection string             |
| `REDIS_URL`         | Yes      | Redis connection string                  |
| `RABBIT_URL`        | Yes      | RabbitMQ connection string               |
| `TAVILY_API_KEY`    | Yes      | API key for Tavily web search            |
| `SECRET_KEY`        | Yes      | JWT signing secret                       |
| `POSTGRES_USER`     | Yes      | PostgreSQL username (for Docker)         |
| `POSTGRES_PASSWORD` | Yes      | PostgreSQL password (for Docker)         |
| `POSTGRES_DB`       | Yes      | PostgreSQL database name (for Docker)    |
| `FRONTEND_URL`      | No       | Frontend origin for CORS configuration   |

---

## Getting Started

### Prerequisites

- Docker and Docker Compose installed
- API keys for Groq, Google Gemini, and Tavily

### Running the Application

```bash
# Start all services (database, cache, message queue, API, workers)
docker compose up -d

# Check API logs
docker compose logs -f api

# Check worker logs
docker compose logs -f worker_generation

# Monitor Celery task execution via Flower dashboard
# Open http://localhost:5555 in your browser

# Scale generation workers if needed
docker compose up -d --scale worker_generation=3
```

### Service Ports

| Service    | Port  | Description                          |
|------------|-------|--------------------------------------|
| API        | 8000  | FastAPI application                  |
| PostgreSQL | 5433  | Database (mapped from internal 5432) |
| Redis      | 6379  | Cache and streaming                  |
| RabbitMQ   | 5672  | Message broker                       |
| Flower     | 5555  | Celery monitoring dashboard          |

---

## API Endpoints

| Method | Path                | Description                        |
|--------|---------------------|------------------------------------|
| GET    | `/`                 | Health check / root                |
| GET    | `/health`           | Service health status              |
| POST   | `/users/`           | User registration                  |
| POST   | `/users/token`      | Authentication (JWT)               |
| POST   | `/conversation/`    | Submit content generation request  |
| GET    | `/conversation/`    | Retrieve generation results        |
| POST   | `/documents/`       | Upload brand documents             |
| GET    | `/documents/`       | List uploaded documents            |

---

## Testing

### Evaluation Framework

The project includes a DeepEval-based evaluation suite that measures:

- **Brand Voice Consistency** -- Does the generated content match the demonstrated brand voice?
- **RAG Retrieval Quality** -- Does the vector search return contextually relevant chunks?
- **Content Faithfulness** -- Does the generated content stay faithful to retrieved context without hallucinating?

```bash
# Run evaluation suite
python evalution.py
```

### Chaos Engineering

The `chaos_engineering/` directory contains four resilience experiments:

1. **Worker Crash Recovery** -- Verifies that tasks are retried and completed when a worker crashes mid-execution.
2. **Redis Restart Recovery** -- Tests system behavior when Redis goes down and comes back.
3. **Data Integrity Under Failure** -- Validates that database writes remain consistent during infrastructure failures.
4. **Latency Injection** -- Measures system behavior under artificially degraded network conditions.

### Unit Tests

```bash
# Run unit tests
pytest tests/
```

---

## Project Structure

```
BrandGuideAI/
  main.py                  # FastAPI application entry point
  database.py              # SQLAlchemy models and database configuration
  model.py                 # LLM provider abstraction (Gemini, Groq, OpenAI, Ollama)
  brand_rag.py             # RAG system (vector search over uploaded documents)
  brand_metrics.py         # Brand metrics extraction, synthesis, and Brand Brain
  celery_task.py           # Celery task definitions and queue configuration
  learning_memory.py       # Generation feedback storage and pattern analysis
  human_loop.py            # Human-in-the-loop re-generation logic
  schema.py                # Pydantic request/response schemas
  auth.py                  # JWT authentication utilities
  Settings.py              # Application configuration (pydantic-settings)
  search.py                # Tavily web search integration
  chunking_stategy.py      # Content-type-aware chunking strategies
  embedding_stategy.py     # Self-hosted embedding model configuration
  limiter.py               # Rate limiting configuration
  graph/
    graph.py               # LangGraph pipeline construction and wiring
    state.py               # Graph state type definition
  nodes/
    researcher.py          # Research agent (RAG + optional web search)
    writer.py              # Content generation agent
    enforcer.py            # Quality scoring and brand compliance agent
    deployer.py            # Persistence, notification, and promotion agent
  prompts/
    researcher.py          # Research summary prompt templates
    writer.py              # Content generation prompt templates
    enforcer.py            # Scoring and enforcement prompt templates
    metrics.py             # Brand metrics extraction and synthesis prompts
  routers/
    users.py               # User registration and authentication endpoints
    conversation.py        # Content generation and retrieval endpoints
    document.py            # Document upload and management endpoints
  frontend/               # React + TypeScript + Vite SPA
  tests/                  # Unit and integration tests
  chaos_engineering/      # Resilience testing experiments
  docker-compose.yml      # Multi-container deployment configuration
  dockerfile              # Application container build instructions
```

---

## License

This project is proprietary. All rights reserved.
