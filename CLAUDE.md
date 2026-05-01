# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

### Development
```bash
# Start backend API (with hot reload)
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Start frontend interface
streamlit run frontend.py

# Start both services (Windows)
.\start_services.bat

# Install dependencies
pip install -r requirements.txt

# Run optimization tests (requires backend running)
python test_optimization.py
```

### API Endpoints
```bash
# Health check
GET /health

# Performance metrics
GET /metrics

# Stream chat (core RAG endpoint)
POST /chat/stream

# Upload documents
POST /upload

# Check task status
GET /task_status/{task_id}

# Clear database
DELETE /clear_db
```

## Architecture Overview

This is a modular RAG (Retrieval-Augmented Generation) system for Wi-Fi protocol knowledge Q&A, built with FastAPI and LangChain.

### Core Modules (`rag_modules/`)

- **data_preparation.py**: Document upload pipeline with MD5 deduplication, PyMuPDF4LLM parsing, and chunking. Manages background task status via `TASK_STATUS` dict.

- **index_construction.py**: Manages vector storage (ChromaDB), BM25 retriever with jieba Chinese tokenization, and model caching. All heavy models (embeddings, cross_encoder, vectorstore, bm25) are cached globally as singletons.

- **retrieval_optimization.py**: Three-tier routing system (LRU cache → keyword matching → LLM), hybrid retrieval (BM25 + vector ensemble), MultiQuery expansion, and result caching with LRU + TTL + DB generation versioning.

- **generation_integration.py**: LLM integration with DeepSeek API, streaming response handling, and chain creation for both chitchat and RAG modes.

- **evaluation.py**: Offline retrieval quality evaluation with Recall@K/MRR/NDCG metrics, LLM-as-Judge scoring, and A/B comparison framework.

### Request Flow

1. **Routing Decision** (`retrieval_optimization.py`): Three-layer routing returns `(route_result, route_source)` where route_result=0 (chitchat) or 1 (technical), route_source=cache/local_rule/llm

2. **Chitchat Path**: Direct LLM response without retrieval

3. **Technical Path (RAG)**:
   - Check retrieval result cache first (LRU + TTL + generation version)
   - If miss: hybrid retrieval (BM25 + vector ensemble)
   - MultiQuery expansion (skipped when query_count=1)
   - CrossEncoder reranking (async via asyncio.to_thread)
   - Stream generation with context

### Cache Invalidation

When documents are uploaded, the retrieval result cache must be invalidated via:
```python
from rag_modules.retrieval_optimization import RETRIEVAL_CACHE
RETRIEVAL_CACHE.invalidate()  # Increments generation, invalidating all cached results
```

When clearing databases, call `index_construction.clear_all_caches()` to reset all model caches.

### Configuration

All constants are centralized in `config.py`:
- Database path: `DB_PATH`
- Model names: `EMBEDDING_MODEL_NAME`, `RERANKER_MODEL_NAME`
- Retrieval params: `BM25_K`, `VECTOR_K`, `ENSEMBLE_WEIGHTS`, `RERANKER_TOP_N`
- Cache params: `CACHE_SIZE_LIMIT`, `RETRIEVAL_CACHE_MAXSIZE`, `RETRIEVAL_CACHE_TTL_SECONDS`

### Critical Implementation Details

- **BM25 Chinese Tokenization**: Uses `jieba_tokenizer` (jieba.lcut) instead of space splitting. Must be passed as `preprocess_func` to BM25Retriever.

- **ChromaDB Singleton**: `get_vectorstore()` caches the Chroma instance globally to avoid repeated SQLite connection overhead. Call `clear_vectorstore_cache()` after DB modifications.

- **Async Reranking**: `AsyncCrossEncoderReranker` wraps sync CrossEncoder inference with `asyncio.to_thread()` to avoid blocking the event loop during concurrent requests.

- **Simple Query Optimization**: When `multi_query_count=1`, MultiQuery expansion is skipped entirely, saving one LLM call.

- **LRU Cache**: Custom `LRUCache` class uses `OrderedDict` and `move_to_end()` for O(1) access, evicts oldest entry when full to prevent cache avalanche.

### Performance Monitoring

`performance_monitor.py` tracks:
- P50/P90/P99 latency percentiles
- Stage-level breakdown (routing, retriever_creation, generation)
- Router cache hit rate, LLM route call rate
- Retrieval cache hit/miss stats

Access via `GET /metrics` endpoint.

### Environment Variables

Required in `.env`:
```
OPENAI_API_KEY=sk-your-deepseek-key
GEMINI_API_KEY=your_gemini_key (optional)
```

HuggingFace mirror is configured: `os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'`
