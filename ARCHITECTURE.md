# System Architecture Manual

This document outlines the system architecture, component layout, and data pipeline flows of the Website RAG Assistant. It serves as a technical onboarding reference for new developers joining the project.

---

## Component Layout

The system is divided into two distinct services: a **FastAPI backend** handling indexing, retrieval, and generation; and a **Next.js frontend** serving the conversational and management interfaces.

```mermaid
graph TD
    subgraph Frontend [Next.js Client]
        UI[User Interface - React components]
        State[Conversation Provider - Shared state]
        SSE[SSE Consumer - useChatStream hook]
        APIClient[API Wrapper - fetch client]
    end

    subgraph Backend [FastAPI Server]
        Router[API Routers - chat, ingest, health, retrieve]
        Core[Core - configuration, logger, container]
        
        subgraph Services [Service Layer]
            Crawl[Web Crawler]
            Chunk[Document Chunker]
            Embed[Embedding Pipeline]
            FAISS[(FAISS Vector Store)]
            Pipeline[RAG Pipeline]
            Retriever[Vector Retriever]
            Gemini[Gemini Client]
        end
    end

    UI --> State
    UI --> SSE
    SSE --> APIClient
    APIClient -->|HTTP / SSE| Router
    Router --> Services
    
    Crawl --> Chunk
    Chunk --> Embed
    Embed --> FAISS
    
    Pipeline --> Retriever
    Pipeline --> Gemini
    Retriever --> FAISS
```

---

## 1. System Components

### Frontend Components
- **`ConversationProvider`**: Shared React context tracking conversation metadata (IDs, titles, active messages). It synchronizes modifications automatically with `localStorage` and exposes state hooks to subcomponents.
- **`Sidebar`**: Left-side layout panel displaying the conversation list, search utility, creation controls, and a redirect trigger pointing to `/indexing`.
- **`ChatWindow`**: Conversational frame consuming real-time Server-Sent Events (SSE). Renders markdown messages with responsive citations and floating auto-scroll controls.
- **`IndexWebsiteClient`**: Page view validating domain inputs, invoking crawling processes, and outputting execution milestones.

### Backend Components
- **Lifespan Manager**: Context manager controlling FastAPI hooks. Validates Google Gen AI model parameters on startup and runs index synchronization tasks to disk during shutdown.
- **Async Crawler**: Scraping engine fetching HTML content using `httpx` and `BeautifulSoup4`. Isolates domains and overrides default HTTP user-agent headers.
- **Document Chunker**: Splitter partitioning documents by paragraphs and sentence tokens. Calculates deterministic ID values using a SHA-256 scheme.
- **Embedding Pipeline**: Engine processing content vectors via `gemini-embedding-001`. Implements thread pools, batch processing, and internal RAM caching.
- **FAISS Vector Store**: Flat index (`IndexFlatIP`) matching query targets using cosine distance logic. Updates persistent metadata sidecars (`metadata.json`).
- **Retrieval Engine**: Multi-mode retrieval service performing similarity matching, metadata checks, and Max Marginal Relevance (MMR) filtering.
- **RAG Coordinator**: Engine stitching retrieval contexts into structured prompts, initiating generative calls to `gemini-3.5-flash`, and parsing citation URLs from outputs.

---

## 2. Sequence Diagram (Full Cycle)

The interaction pattern between the user, the frontend client, the FastAPI endpoints, local indexes, and the external Gemini APIs:

```mermaid
sequenceDiagram
    autofunc
    actor User
    participant FE as Next.js Client
    participant BE as FastAPI Backend
    participant DB as FAISS Vector Store
    participant Gemini as Google Gemini API

    %% Indexing Pipeline Sequence
    rect rgb(240, 240, 245)
        Note over User, Gemini: 1. Website Indexing Flow
        User->>FE: Submit URL (https://docs.python.org/3/)
        FE->>BE: POST /api/ingest {urls, max_depth}
        activate BE
        BE->>BE: Async crawl seed URL (httpx + BeautifulSoup)
        BE->>BE: Partition texts (RecursiveCharacterTextSplitter)
        BE->>Gemini: Request embeddings (gemini-embedding-001)
        Gemini-->>BE: Return vectors (768-dim)
        BE->>DB: Add vectors & metadata to FAISS flat index
        BE->>DB: Write index.faiss & metadata.json to disk
        BE-->>FE: Return completed status & counts
        deactivate BE
        FE-->>User: Render ingestion statistics
    end

    %% Chat Pipeline Sequence
    rect rgb(245, 240, 240)
        Note over User, Gemini: 2. Chat / RAG Retrieval & Generation Flow
        User->>FE: Ask: "What is Python?"
        FE->>BE: POST /api/chat {query, stream: true}
        activate BE
        BE->>Gemini: Generate query embedding (RETRIEVAL_QUERY)
        Gemini-->>BE: Return query vector
        BE->>DB: Search query vector in FAISS FlatIP index
        DB-->>BE: Return nearest chunks + metadata scores
        BE->>BE: Format prompt with context & grounding rules
        BE->>Gemini: Stream prompt (gemini-3.5-flash)
        activate Gemini
        loop Token Stream
            Gemini-->>BE: Stream token chunks
            BE-->>FE: SSE data chunk event
            FE-->>User: Append text in real-time
        end
        deactivate Gemini
        BE-->>FE: SSE done event (citations metadata)
        deactivate BE
        FE-->>User: Render formatted markdown & source links
    end
```

---

## 3. Website Indexing Pipeline

Processing details for ingested URLs:

```mermaid
graph TD
    Start[Ingest Request] --> UrlVal{Valid HTTP/S Link?}
    UrlVal -->|No| Fail[Return 400 Bad Request]
    UrlVal -->|Yes| Client[Build httpx.AsyncClient + Bot User-Agent]
    
    Client --> Loop[Pop Pending Crawl Queue]
    Loop --> Fetch[Fetch HTML Page]
    Fetch --> BS4[Clean HTML - bs4]
    BS4 --> Deduplicate{Duplicate Text Hash?}
    
    Deduplicate -->|Yes| Skip[Skip Page Content]
    Deduplicate -->|No| Store[Save raw document metadata]
    
    Store --> Chunk[LangChain Chunker]
    Chunk --> Cache{Match In-Memory Cache?}
    
    Cache -->|Yes| Hit[Retrieve Cached Vector]
    Cache -->|No| Embed[Batch Request: gemini-embedding-001]
    
    Embed --> Normalize[L2 Cosine Normalization]
    Hit --> Normalize
    
    Normalize --> Index[Insert vectors to FAISS FlatIP index]
    Index --> Save[Commit index.faiss & metadata.json to disk]
    Save --> End[Return completed counts]
```

---

## 4. Chat Request Pipeline

Processing flow for query generation:

```mermaid
graph TD
    Request[Chat Query: POST /api/chat] --> Search{Vector database empty?}
    Search -->|Yes| NoContext[Skip RAG -> Generate with zero context]
    Search -->|No| Embed[Convert query string to vector]
    
    Embed --> FAISS[Search FAISS flat index]
    FAISS --> Filter{Metadata filters present?}
    
    Filter -->|Yes| PostFilter[Remove mismatched chunk tags]
    Filter -->|No| Strategy{MMR Re-ranking enabled?}
    PostFilter --> Strategy
    
    Strategy -->|Yes| MMR[Compute MMR relevance/diversity tradeoff]
    Strategy -->|No| TopK[Select top-k scored chunks]
    MMR --> Prompt[Stitch context chunks into prompt template]
    TopK --> Prompt
    
    Prompt --> Stream{Client requests SSE stream?}
    
    Stream -->|Yes| SSE[Stream tokens via FastAPI StreamingResponse]
    Stream -->|No| NonSSE[Block & return complete ChatResponse JSON]
    
    SSE --> Parse[Extract inline citations & source URLs]
    NonSSE --> Parse
    Parse --> Display[Render chat UI with active Markdown links]
```

---

## 5. Streaming Implementation

Streaming is implemented using FastAPI `StreamingResponse` on the backend and Server-Sent Events (SSE) on the frontend:

- **Thread-Safe Stream Capture**: The Google GenAI SDK methods are synchronous. To stream tokens dynamically without locking Uvicorn event loops, the backend launches `generate_content_stream` inside a Python executor thread.
- **Asynchronous Queue Pipeline**: Partial response chunks are captured in the background thread and written directly to an `asyncio.Queue`. The FastAPI route generator reads tokens from this queue and outputs standard SSE lines: `data: {"event": "token", "text": "..."}`.
- **Cancellation Monitoring**: The backend generator listens to request disconnect events. If a user interrupts the generation or closes the page, the backend task terminates the queue iteration and closes the generation worker thread.
- **Client Handler**: The frontend `useChatStream` hook uses the browser's `fetch` API. It reads the raw HTTP readable stream, translates chunks using `TextDecoder`, splits them by `data:` markers, and appends the tokens to the active message window in real-time.

---

## 6. Conversation State Management

Conversation state is managed in the frontend layout to ensure layout elements remain synchronized:

- **State Sync**: Conversation structures (ID, title, message lists, update timestamps) are stored in local storage and managed via React Context.
- **Centralized Event Processing**: Component modifications (creating new threads, selecting conversations, renaming, deleting) route through the provider hooks, modifying the state in one place to update all layout components simultaneously.
- **Routing Rules**: The sidebar and chat components are linked via Next.js routes. The sidebar acts as a global navigator; if a user performs actions (creating a chat or clicking a historical log) while on the `/indexing` view, the sidebar automatically redirects the viewport to `/chat`.

---

## 7. Folder Dependency Graph

Folder structural relationship and flow dependencies:

```mermaid
graph TD
    subgraph root [Project Root]
        compose[docker-compose.yml]
        render[render.yaml]
        vercel[vercel.json]
    end

    subgraph FE [Frontend Workspace]
        app[app/ - Next.js Router]
        components[components/ - Sidebar, Chat, UI]
        hooks[hooks/ - useChatStream, useConversation]
        services[services/ - API REST client]
        stores[stores/ - Zustand stores]
        providers[providers/ - Theme & Context state]
        
        app --> components
        app --> providers
        components --> hooks
        hooks --> services
        services --> providers
    end

    subgraph BE [Backend Workspace]
        main[main.py - Lifecycle & Middlewares]
        api[api/ - Routers & Schemas]
        core[core/ - Config, Container, Logger]
        services_be[services/ - Crawler, FAISS, Gemini]
        
        main --> api
        main --> core
        main --> services_be
        api --> services_be
        api --> core
        services_be --> core
    end

    services -->|REST / SSE requests| main
    compose -->|Spins up containers| Dockerfile_BE[backend/Dockerfile]
    compose -->|Spins up containers| Dockerfile_FE[frontend/Dockerfile]
```

---

## 8. Deployment Architecture

Deployments are structured to handle frontend edge caching and persistent database requirements for local filesystems:

```
                  +--------------------------------+
                  |       Vercel Edge Network      |
                  |  - Next.js static asset build  |
                  |  - /api Rewrites to Backend    |
                  +--------------------------------+
                                  │
                          HTTPS API Request
                                  ▼
                  +--------------------------------+
                  |     Render Web Service         |
                  |  - Single-worker Docker ASGI   |
                  |  - FastAPI Application         |
                  +--------------------------------+
                                  │
                           Reads/Writes to
                                  ▼
                  +--------------------------------+
                  |      Render Persistent Volume   |
                  |  - Mounted at /app/vector_store|
                  |  - Stores index.faiss & JSON   |
                  +--------------------------------+
```

- **Vercel edge hosting**: The Next.js code is optimized for serverless deployments on Vercel. A rewrite rule inside `vercel.json` proxies API calls matching `/api/*` directly to the backend domain, avoiding CORS preflight checks.
- **Render persistent instances**: The backend container runs as a single-process service. It utilizes Render persistent volumes mapped to `/app/vector_store` to ensure the FAISS files survive container updates and service restarts.
- **Docker virtualization**: Local environments mirror the production deployment configuration using docker-compose networks to link the services together.
