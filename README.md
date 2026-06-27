# Website RAG Assistant

A production-ready, full-stack Retrieval-Augmented Generation (RAG) assistant designed to crawl websites, index their content, and provide contextual answers with precise source citations. 

The application utilizes a **FastAPI** backend for heavy lifting—crawling, semantic chunking, generating embeddings, and vector similarity search—and a modern **Next.js** frontend with a responsive, dark-mode-first chat interface inspired by state-of-the-art AI applications.

---

## Features

- **Website Crawling**: Asynchronous recursive web crawler (using `BeautifulSoup4` and `httpx`) that respects domain boundaries and obeys a user-defined max crawl depth. Incorporates browser-like `User-Agent` headers to successfully bypass anti-bot scrapers (such as Wikipedia).
- **Intelligent Chunking**: Implements LangChain's `RecursiveCharacterTextSplitter` to semantically divide raw HTML body text by structured paragraphs, sentences, and words. Generates deterministic SHA-256 hashes to prevent duplicate ingestion.
- **Gemini Embeddings**: Integrates the official `google-genai` SDK to convert text chunks into dense 768-dimensional vectors using `gemini-embedding-001`. Features thread-pooled batching, exponential back-off retries for rate limits, and an in-memory caching layer.
- **Gemini Chat**: Answers user queries dynamically using `gemini-3.5-flash` grounded strictly on retrieved website context, automatically declining to answer if context is insufficient.
- **FAISS Vector Search**: Leverages local `faiss-cpu` vector indexes using L2-normalized Inner Product similarity (`IndexFlatIP`) for rapid vector similarity calculations coupled with JSON-based sidecar metadata persistence.
- **Source Citation Retrieval**: Automatically extracts cited source URLs inline and appends a "Sources" list containing active links to the pages the LLM used for answers.
- **Streaming Responses**: Real-time streaming via Server-Sent Events (SSE) from FastAPI to the frontend, complete with active generation cancellation capabilities.
- **Website Indexing UI**: Dedicated frontend interface (`/indexing`) providing URL validation, real-time crawler states, and a breakdown of crawled pages, chunks created, and vectors indexed.
- **Conversation Management**: Sidebar history supporting custom conversation titles, renaming, deleting, and state synchronization across components powered by React Context and Zustand.
- **Responsive UI**: Sleek layout crafted with Vanilla CSS and Tailwind, supporting collapsible sidebars, smooth desktop layouts, and a responsive mobile drawer.
- **Dark Mode**: Comprehensive visual consistency utilizing light and dark theme configurations with clean CSS variables.
- **Health Monitoring**: System status metrics endpoint returning vector store sizes, embedding cache hit metrics, configuration variables, and general liveness stats.

---

## System Architecture

The following diagram illustrates the flow of data from ingestion (crawling/indexing) through query retrieval and generation:

```mermaid
graph TD
    %% Ingest Pipeline
    UserIngest[User enters URL in Indexing UI] -->|POST /api/ingest| IngestRoute[FastAPI Ingest Route]
    IngestRoute -->|Execute Crawl| Crawler[Async Crawler (BeautifulSoup4 + httpx)]
    Crawler -->|Extract raw HTML/Text| Chunker[Semantic Chunker (RecursiveCharacterTextSplitter)]
    Chunker -->|Compute Text Vectors| EmbedPipe[Embedding Pipeline (gemini-embedding-001)]
    EmbedPipe -->|Save Vector Index| FAISS[(FAISS Vector Store)]
    
    %% RAG Chat Query Pipeline
    UserQuery[User types question in Chat UI] -->|POST /api/chat (stream=true)| ChatRoute[FastAPI Chat Route]
    ChatRoute -->|Embed Query| EmbedQuery[Query Embedding (RETRIEVAL_QUERY)]
    EmbedQuery -->|Cosine Similarity Search| FAISS
    FAISS -->|Retrieve Top K + Metadata| Retriever[Metadata Filter / MMR Retriever]
    Retriever -->|Construct Grounded Prompt| PromptEngine[Prompt Construction]
    PromptEngine -->|Request Completion| GeminiGen[Gemini LLM (gemini-3.5-flash)]
    GeminiGen -->|Stream SSE Event Chunks| SSE[Response with Citations]
    SSE -->|Render Inline Markdown| UserQuery
```

---

## Technology Stack

- **Languages**: Python (3.12+), TypeScript, CSS, HTML
- **Frontend**: 
  - Next.js 14 (App Router)
  - React 18
  - Zustand (UI state)
  - React Context (Conversation state)
  - Framer Motion (Animations)
  - TailwindCSS
- **Backend**:
  - FastAPI (REST API & Server-Sent Events)
  - Uvicorn (ASGI server)
  - Pydantic v2 (Data validation and settings)
  - Dependency Injector (IoC Container)
  - Structlog (Structured JSON logging)
- **AI & Vector DB**:
  - Google Gen AI SDK (`google-genai` package)
  - LangChain (for `RecursiveCharacterTextSplitter`)
  - FAISS (`faiss-cpu`) for local, fast vector storage
- **Deployment**:
  - Vercel (Frontend Hosting)
  - Render (Backend Web Service with Persistent Disk)
  - Docker & Docker Compose (Local Orchestration)

---

## Folder Structure

```text
website-rag/
├── backend/
│   ├── app/
│   │   ├── api/             # HTTP Route Handlers (chat, ingest, health, retrieve)
│   │   │   ├── schemas.py   # Pydantic input/output validation models
│   │   ├── core/            # App lifecycle hooks, logger configurations, settings
│   │   │   ├── config.py    # Environment variable loading & default configurations
│   │   ├── services/        # Business logic handlers
│   │   │   ├── chunking.py     # Document partition logic
│   │   │   ├── embeddings.py   # Google GenAI embedding generator
│   │   │   ├── ingestion.py    # Recursive web crawler
│   │   │   ├── rag_pipeline.py # Grounded prompt generation & chat coordinator
│   │   │   ├── retrieval.py    # Similarity & MMR search logic
│   │   │   ├── storage.py      # Persistence file handlers
│   │   │   └── vector_store.py # Local FAISS integration and persistence
│   │   └── main.py          # ASGI application entry point & middlewares
│   ├── Dockerfile           # Multi-stage production-ready build
│   └── requirements.txt     # Locked python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router (Layouts & Routes)
│   │   │   ├── chat/        # Chat window view
│   │   │   ├── indexing/    # Website index administrator dashboard
│   │   │   ├── globals.css  # Application style rules
│   │   │   └── page.tsx     # Application redirect logic
│   │   ├── components/      # UI Components (Sidebar, ChatWindow, ui/ components)
│   │   ├── hooks/           # Custom React hooks (useChatStream, useConversation)
│   │   ├── lib/             # Utility clients and helper configurations
│   │   ├── providers/       # State providers (ThemeProvider, ConversationProvider)
│   │   ├── services/        # Frontend API client wrappers
│   │   └── stores/          # Zustand global stores (Sidebar state)
│   └── Dockerfile           # Node production server configuration
├── docker-compose.yml       # Local development multi-container setup
├── render.yaml              # Infrastructure-as-code for Render
└── vercel.json              # Vercel proxy configurations
```

---

## Installation & Setup

### Environment Variables
Configure a `.env` file in the root directory. Use `.env.example` as a template:

```bash
# Frontend configurations
NEXT_PUBLIC_API_URL=http://localhost:8000/api

# Backend configurations
GEMINI_API_KEY=your_google_gemini_api_key
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
VECTOR_STORE_PATH=data/vector_store
LOG_LEVEL=INFO
```

### Local Development (Using Docker Compose)
The easiest way to boot the application stack locally is using Docker Compose:

```bash
# 1. Clone the repository and configure environment variables
cp .env.example .env

# 2. Spin up the backend and frontend services
docker-compose up --build
```
- **Frontend App**: `http://localhost:3000`
- **FastAPI Documentation**: `http://localhost:8000/docs`
- **Backend API**: `http://localhost:8000/api`

### Manual Development Setup

#### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## Deployment

### Frontend (Vercel)
Deploy the Next.js frontend to **Vercel** with the following steps:
1. Connect your repository to Vercel.
2. Set the Framework Preset to **Next.js**.
3. In **Environment Variables**, add:
   - `NEXT_PUBLIC_API_URL`: Your deployed FastAPI backend URL, including the `/api` segment (e.g., `https://your-api.onrender.com/api`).
4. Click **Deploy**. Vercel will build the production standalone distribution.

### Backend (Render)
Deploy the FastAPI backend utilizing Render's Blueprint.
1. Connect your repository to **Render** and deploy using the `New > Blueprint` flow.
2. Render automatically reads render.yaml and provisions:
   - A Web Service built with `backend/Dockerfile`.
   - A 1GB persistent disk mapped to `vector_store` so FAISS vector databases persist across deployments.
3. Configure the following variables inside the **Render Dashboard**:
   - `GEMINI_API_KEY`: Securely configure your Google Gemini API Key.
   - `CORS_ORIGINS`: Point to your production Vercel frontend URL (no trailing slash). E.g., `https://your-app.vercel.app,http://localhost:3000`.

---

## API Endpoints

### `POST /api/ingest`
Submits a URL (or list of URLs) to crawl, chunk, embed, and store.
- **Request Body**:
  ```json
  {
    "urls": ["https://docs.python.org/3/"],
    "max_depth": 2,
    "chunk_size": 1000,
    "chunk_overlap": 200
  }
  ```
- **Response**:
  ```json
  {
    "status": "completed",
    "pages_crawled": 1,
    "chunks_created": 5,
    "chunks_embedded": 5,
    "chunks_indexed": 5
  }
  ```

### `POST /api/chat`
Ask questions against the indexed vector store content.
- **Request Body**:
  ```json
  {
    "query": "What is Python?",
    "top_k": 5,
    "stream": true
  }
  ```
- **Response (stream=false)**: Returns a complete `ChatResponse` JSON.
- **Response (stream=true)**: Returns an `EventStream` (SSE) yielding incremental tokens and final source citation links.

### `GET /api/status`
Retrieves indexing stats, local cache sizes, and non-sensitive configurations.

### `GET /api/health`
Liveness check returning `{ "status": "ok" }`.

---

## Screenshots

*Placeholders for interface screenshots:*
- **Chat Window View**: `[docs/screenshots/chat-interface.png]` (Interactive conversation panel)
- **Website Indexing Panel**: `[docs/screenshots/indexing-page.png]` (Crawler pipeline supervisor)

---

## Known Limitations

- **Local Vector Database**: FAISS operates entirely in-memory and persists index updates to a disk file. Consequently, horizontal scaling across multiple containers or instances requires a shared disk storage solution (like Render's persistent disk) or a migration to a managed vector store (e.g., Pinecone/Qdrant).
- **Domain Scraping**: The asynchronous crawler limits crawling to pages matching the root seed host to prevent infinite traversal. Highly complex JavaScript dynamic rendered pages might not extract completely.

---

## Future Improvements

- **Managed Vector DB Support**: Swapping out local FAISS for a remote cloud database provider by implementing the abstract `BaseVectorStore` class.
- **Hybrid Search Capabilities**: Merging dense vector semantic retrieval with classic BM25 keyword matching for superior recall scores.
- **Document Uploader**: Expanding crawler scopes to ingest PDF, CSV, and docx files directly via drag-and-drop.

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.
