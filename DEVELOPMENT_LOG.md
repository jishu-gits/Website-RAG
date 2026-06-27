# Website RAG Development Log

This document serves as the official engineering log and technical notebook for the Website RAG Assistant project. It charts the goals, architecture, chronological implementation details, deployment decisions, and debugging history of the system.

---

## Project Goal
The target of this project was to build a production-grade, highly responsive Retrieval-Augmented Generation (RAG) assistant. The application allows users to submit a website URL, automatically crawl and index its contents, and query an LLM (Google Gemini) that generates answers strictly grounded on the crawled data. Key constraints included source citation rendering, SSE streaming, full conversation state persistence, and cross-platform deployment capability.

---

## Overall Architecture
The system utilizes a decoupled, client-server model:

```
+--------------------------------------------------------+
|                      Next.js Frontend                  |
|  - Chat Interface & Sidebar History (React + Context)  |
|  - Website Indexing UI (/indexing)                     |
|  - SSE Streaming Consumer (useChatStream hook)         |
+--------------------------------------------------------+
                           │
                 HTTP REST / SSE Stream
                           ▼
+--------------------------------------------------------+
|                     FastAPI Backend                    |
|  - Endpoint Routers (/chat, /ingest, /status, /health)  |
|  - CORS & Secure Headers Middleware                    |
+--------------------------------------------------------+
       │                     │                      │
       ▼                     ▼                      ▼
+─────────────+       +──────────────+       +──────────────+
|   Crawler   |       | Vector Store |       |  Generation  |
| - BeautifulSoup4    | - FAISS      |       | - Google Gen |
| - httpx Bot |       | - JSON Meta  |       |   AI Client  |
+─────────────+       +──────────────+       +──────────────+
```

---

## Development Timeline

### Phase 1: Backend Architecture
*   **Goal**: Establish a robust, high-performance ASGI application skeleton with dependency injection, configuration safety, structured JSON logging, and lifecycle hooks.
*   **Implementation**: Configured FastAPI with Pydantic Settings (`Settings` class) to manage environment variables automatically. Registered structured logging via `structlog` and established a lifespan hook to handle database loads on boot and index flushes on shutdown.
*   **Files Modified**: `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/core/logger.py`
*   **Challenges**: Structlog configuration conflicts with default Uvicorn handlers, leading to double-logged entries.
*   **Root Cause**: Both FastAPI and Uvicorn were attempting to hook stdout.
*   **Solution**: Disabled default Uvicorn logger formatting configurations and explicitly passed formatted dictionary schemas to Python's logging core.
*   **Lessons Learned**: Centralizing configs via Pydantic prevents silent configuration failures at runtime.

### Phase 2: Crawler
*   **Goal**: Implement an asynchronous crawler capable of recursively traversing a seed URL up to a configured max depth.
*   **Implementation**: Built an asynchronous crawling engine utilizing `httpx.AsyncClient` and a semaphore to limit concurrent requests. Parsed pages using `BeautifulSoup4` to decompose scripts, style sheets, and noscripts, extracting titles, headings, and raw text.
*   **Files Modified**: `backend/app/services/ingestion.py`
*   **Challenges**: Crawling targets like Wikipedia returned immediate `403 Forbidden` responses.
*   **Root Cause**: Wikipedia and many cloud proxy platforms block requests containing default HTTP client headers (or missing user-agents) to mitigate scraping scripts.
*   **Solution**: Configured the `httpx.AsyncClient` initialization context to pass a custom, browser-like `User-Agent` header (`Mozilla/5.0 (compatible; WebsiteRAGBot/1.0...)`).
*   **Lessons Learned**: Web scraping client interfaces must simulate standard user browser headers to ensure reliability.

### Phase 3: Chunking
*   **Goal**: Break extracted website texts into logical, semantic pieces while retaining metadata.
*   **Implementation**: Built a chunking service around LangChain's `RecursiveCharacterTextSplitter`. Set separators hierarchy (`\n\n`, `\n`, `. `, ` `, `""`) to preserve paragraph and sentence structure, and wrote a nearest-heading trace algorithm to pass heading paths down with the metadata.
*   **Files Modified**: `backend/app/services/chunking.py`
*   **Challenges**: Determining a stable, collision-free identification mechanism for duplicate verification.
*   **Root Cause**: Simple incremental integer IDs led to collisions across distinct URLs.
*   **Solution**: Constructed a deterministic SHA-256 hash using the parent document's URL combined with the chunk's relative index: `_generate_chunk_id(url, idx)`.
*   **Lessons Learned**: Semantic boundaries maintain text meaning far better than fixed character count thresholds.

### Phase 4: Embeddings
*   **Goal**: Convert text segments into high-quality vectors with rate limit safety.
*   **Implementation**: Implemented embedding functions targeting `gemini-embedding-001`. Wrote a batch processing loop to segment chunks according to batch capacity limits, and added thread-pooling (`asyncio.to_thread`) to run synchronous SDK processes without blocking FastAPI event loops.
*   **Files Modified**: `backend/app/services/embeddings.py`
*   **Challenges**: Permanent API failures due to deprecation of the older model `text-embedding-004` and legacy client interfaces.
*   **Root Cause**: The Google legacy `google-generativeai` SDK interface and the model `text-embedding-004` were retired in early 2026.
*   **Solution**: Upgraded to the modern `google-genai` SDK and shifted targeting to the `gemini-embedding-001` model.
*   **Lessons Learned**: Critical cloud service clients should be isolated behind wrapper functions to simplify future API migrations.

### Phase 5: FAISS (Vector Store)
*   **Goal**: Local, high-speed vector index with search capability and disk persistence.
*   **Implementation**: Created a `FAISSVectorStore` executing inner product (`IndexFlatIP`) matching for normalized L2 cosine similarity search. Embedded a sidecar metadata persistence layer writing index structures to `.faiss` and structured metadata maps to `.json`.
*   **Files Modified**: `backend/app/services/vector_store.py`
*   **Challenges**: Vector database state returned 0 objects upon restarts inside containerized/PaaS runtimes.
*   **Root Cause**: Local filesystems in standard cloud containers are ephemeral; vector store disk commits were lost upon restarts.
*   **Solution**: Mounted persistent volume directories (`/data`) on Render and configured the `VECTOR_STORE_PATH` settings to write updates inside that directory.
*   **Lessons Learned**: Vector directories must map to persistent storage blocks in serverless or containerized environments.

### Phase 6: Retriever
*   **Goal**: Filter, fetch, and rank vector contents relative to queries.
*   **Implementation**: Built a retrieval layer matching query embeddings against vectors in the database. Added a custom implementation of Max Marginal Relevance (MMR) re-ranking alongside classic similarity matching to achieve content diversity and avoid duplicate inputs to the context window.
*   **Files Modified**: `backend/app/services/retrieval.py`
*   **Challenges**: Vector comparison calculations are computationally heavy for large sets when using pure Python structures.
*   **Root Cause**: Matrix loops in vanilla Python introduce blocking overhead.
*   **Solution**: Utilized `numpy` vectorization techniques to format comparison operations, delegating core searches to native C++ FAISS loops.
*   **Lessons Learned**: Cosine distance matrices should always be evaluated in vectorized frameworks.

### Phase 7: Gemini Integration
*   **Goal**: Connect to Gemini models to generate answers with grounding constraints.
*   **Implementation**: Instantiated a `GeminiClient` utilizing `gemini-3.5-flash`. Structured a strict system prompt instructing the model to rely solely on the injected context, return a standard "I don't have enough information" string if the source context does not support the answer, and cite the utilized URLs.
*   **Files Modified**: `backend/app/services/gemini_client.py`
*   **Challenges**: Non-deterministic formats of LLM citation citations broke the parser.
*   **Root Cause**: Prompt instructions were occasionally bypassed, leading to inline formats not conforming to the parser logic.
*   **Solution**: Rewrote prompt rules to require standard Markdown link formats and a distinct "Sources:" section at the end of the text.
*   **Lessons Learned**: Relying on strict prompt instructions is more robust when paired with regex post-processing fallback logic.

### Phase 8: Streaming Chat
*   **Goal**: Deliver tokens in real-time to the client using Server-Sent Events (SSE).
*   **Implementation**: Configured FastAPI `StreamingResponse` outputs consuming an asynchronous queue populated by a background thread executing `client.models.generate_content_stream`. Yielded events formatting token outputs as standard SSE `data: {}` strings.
*   **Files Modified**: `backend/app/api/chat.py`, `backend/app/services/rag_pipeline.py`
*   **Challenges**: Disconnected client sessions leaked running generation threads in the backend.
*   **Root Cause**: FastAPI ASGI streams do not automatically terminate executing generator loops when clients terminate HTTP sockets.
*   **Solution**: Implemented connection state listeners within the event generation loops, returning early and terminating background task executions when clients disconnected.
*   **Lessons Learned**: Streaming endpoints must monitor connection states to prevent resource leaks.

### Phase 9: Frontend
*   **Goal**: Build a clean, responsive web application containing chat panels, themes, and sidebar lists.
*   **Implementation**: Built a Next.js 14 App Router project utilizing TailwindCSS styling and Framer Motion. Handled theme selections between light and dark modes with global CSS variables and configured custom scroll behaviors inside conversation views.
*   **Files Modified**: `frontend/src/app/chat/page.tsx`, `frontend/src/app/globals.css`, `frontend/src/components/ChatWindow.tsx`
*   **Challenges**: Stream responses rendered raw Markdown tags as unformatted text.
*   **Root Cause**: Render templates were simple strings.
*   **Solution**: Integrated `react-markdown` parsing libraries along with `remark-gfm` and `highlight.js` syntax highlight structures.
*   **Lessons Learned**: Sanitizing Markdown parsing results is critical to prevent injection of malicious code.

### Phase 10: Conversation Management
*   **Goal**: Create, select, edit, and persist user conversation threads locally.
*   **Implementation**: Created a `ConversationProvider` context storing state lists containing titles, IDs, and messages. Persisted configurations to `localStorage` and wired Sidebar state items to update on click events.
*   **Files Modified**: `frontend/src/providers/ConversationProvider.tsx`, `frontend/src/components/Sidebar.tsx`
*   **Challenges**: Creating a conversation in the Sidebar failed to trigger text updates in the ChatWindow.
*   **Root Cause**: Both Sidebar and ChatWindow were calling `useConversation()` independently, creating two separate isolated state states instead of sharing a global provider.
*   **Solution**: Refactored states into a unified `ConversationProvider` context wrapping both components in `layout.tsx`.
*   **Lessons Learned**: Shared layout components must consume state from a common ancestor provider context.

### Phase 11: Deployment
*   **Goal**: Deploy the frontend on Vercel and the backend on Render.
*   **Implementation**: Configured `vercel.json` rewrites to proxy `/api` endpoints and structured a `render.yaml` blueprint defining Docker configurations, environment maps, and volume mounts.
*   **Files Modified**: `vercel.json`, `render.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`
*   **Challenges**: Production API calls returned CORS preflight errors.
*   **Root Cause**: The API origin list in the backend was not configured to trust the deployed frontend URL.
*   **Solution**: Configured the backend's `CORS_ORIGINS` variable to read from a comma-separated list of allowed domains, dynamically matching Vercel origins.
*   **Lessons Learned**: CORS declarations must be dynamic, verified during build pipelines, and configurable via dashboard environments.

### Phase 12: Website Indexing UI
*   **Goal**: Interface for administrators to submit URLs and view ingestion logs.
*   **Implementation**: Created `/indexing/page.tsx` containing an URL verification form. The page executes `postIngest` to `/api/ingest` and polls `/api/status` to present vector totals.
*   **Files Modified**: `frontend/src/app/indexing/page.tsx`, `frontend/src/app/indexing/IndexWebsiteClient.tsx`
*   **Challenges**: Production builds failed on Vercel with a `Cannot read properties of undefined (reading 'clientModules')` runtime error.
*   **Root Cause**: Next.js App Router has compiler conflicts with directory routes named `index` (e.g. `app/index`).
*   **Solution**: Renamed the Next.js page route directory from `index` to `indexing` to resolve route conflict.
*   **Lessons Learned**: Avoid naming directory paths with Next.js internal keywords or route reserved terms.

---

# Deployment Journey

### Docker Configuration
Both the backend and frontend are structured using multi-stage Docker builds:
1.  **Backend**: Uses `python:3.12-slim` to minimize the image footprint. Build dependencies (`gcc`, `build-essential`) are installed in a builder phase, compiling wheels and migrating site-packages to a slim runtime image. It uses a non-root user (`appuser`) for security.
2.  **Frontend**: Built for standalone distribution (`output: "standalone"` configured in `next.config.js`), drastically decreasing container weights.

### Render Configuration
Render deployments are managed via a blueprint file (`render.yaml`).
- **Disk Mounts**: A persistent disk of 1GB is mounted to `/app/vector_store` for FAISS index persistence.
- **Environment Handling**: CORS configuration inputs and the Gemini API key are declared as dynamic variables within the dashboard environment to decouple secrets from source code.

### Vercel Configuration
The Vercel environment handles the frontend hosting. An environment variable named `NEXT_PUBLIC_API_URL` points directly to Render's backend domain. To bypass cross-origin requests, a proxy configuration in `vercel.json` maps requests made to `/api/:path*` directly to the Render endpoint.

---

# Debugging Journal

### 1. Gemini SDK Migration
*   **Issue**: Legacy API calls threw compilation errors in `embeddings.py` and `gemini_client.py`.
*   **Symptoms**: Exceptions stating `module 'google.generativeai' has no attribute 'configure'`.
*   **Root Cause**: Google deprecated `google-generativeai` in favor of the new `google-genai` package.
*   **Fix**: Rewrote the client setup logic to utilize the new `Client` structure:
    ```python
    from google import genai
    client = genai.Client(api_key=...)
    ```
*   **Lesson Learned**: Check library support lifecycles before building integrations on legacy codebases.

### 2. Embedding Dimension Mismatch
*   **Issue**: Ingestion calls failed with vector length check exceptions when executing additions to the vector index.
*   **Symptoms**: `Error: dimension mismatch in FAISS: index expected 768 but got 1536`.
*   **Root Cause**: The default configuration was set for 768 dimensions, but the API returned 1536 dimensions due to embedding model defaults.
*   **Fix**: Created a `validate_embedding_model` function in the backend's startup lifespan hook. It executes a test request to ensure returned dimensions match the system settings.
*   **Lesson Learned**: Incorporate sanity checks in the app startup lifecycle to detect configuration mismatches early.

### 3. Isolated State in Conversation Components
*   **Issue**: Sidebar conversation clicks failed to update the active message list in the main chat screen.
*   **Symptoms**: State fields like `activeId` were updated in the Sidebar, but remained `null` in the ChatWindow.
*   **Root Cause**: Both UI elements called `useConversation` independently, creating two separate instances of the React state.
*   **Fix**: Created a `ConversationProvider` context, moving the state initialization to the root layout level so both components access the same state instance.
*   **Lesson Learned**: State must be elevated to a shared provider context when multiple layout blocks need to synchronize.

### 4. Vercel Prerender Failures for `/index`
*   **Issue**: Vercel compilation crashed at the static page generation step.
*   **Symptoms**: `TypeError: Cannot read properties of undefined (reading 'clientModules')`.
*   **Root Cause**: In Next.js App Router, using `index` as a route folder name creates collisions with root `page.tsx` assets in the build manifest.
*   **Fix**: Renamed the route path directory to `/indexing` and modified navigation links.
*   **Lesson Learned**: Do not name app routes with reserved words or filesystem paths that conflict with framework internals.

### 5. Multi-Worker Vector Store Isolation
*   **Issue**: Ingestion returned success status, but immediate status calls reported size 0.
*   **Symptoms**: Vector count matched expectations in the `/api/ingest` response but returned to 0 in `/api/status` or `/api/chat`.
*   **Root Cause**: Uvicorn was spawning multiple worker processes. Since the database was in-memory, updates made on a worker handling `/api/ingest` were missing on the workers handling `/api/status` or `/api/chat`.
*   **Fix**: Limited the local production container to run on a single ASGI worker. The in-memory state remains synchronized within a single process.
*   **Lesson Learned**: Local, in-memory databases require single-process workers, or must be migrated to external, managed database servers to support horizontal scaling.

---

# Engineering Lessons
1.  **Abstract Resource Layers**: Designing the vector store around a `BaseVectorStore` abstract class allowed testing without tying the database logic to a specific provider.
2.  **Validate Dependencies Early**: Startup verification tasks (like sending a test embedding vector) prevent production crashes caused by retired models or invalid keys.
3.  **Strict CORS Design**: CORS configuration should always read from environment lists rather than using wildcards to protect backend resources.
4.  **Isolate Client Elements**: Next.js Server Components should remain thin wrappers importing Client Components to prevent runtime build errors.

---

# Project Retrospective

### What Went Well
- **Asynchronous performance**: The combination of `BeautifulSoup4` and asynchronous requests fetches and indexes pages quickly.
- **SSE Streaming**: Delivering tokens via Server-Sent Events provides a smooth, responsive chat interface.
- **Local FAISS Efficiency**: Using a local vector index avoided network overhead and simplified development.

### What Was Difficult
- **Process Memory Isolation**: Tracking down data loss caused by multi-process workers required careful verification of process IDs.
- **API deprecations**: Upgrading legacy Gemini structures required rewriting the client logic to use the new SDK formats.

### Major Architecture Decisions
- **Unified Conversation Provider**: Elevating conversation state to a shared context resolved synchronization bugs between the sidebar and chat components.
- **Local FAISS flat index**: Choosing local FAISS Flat IP indexes provided exact similarity matching while keeping setup requirements minimal.

### Possible Future Evolution
- **Managed Vector Store Database**: Transitioning from a local FAISS index to a cloud vector database (e.g. Pinecone) to allow scaling across multiple backend instances.
- **Clustered Retrieval**: Combining vector similarity with keyword-based searches to improve document relevance.
- **Multi-Tenant Authentication**: Integrating authentication providers to secure data and isolate indexing profiles per user.
