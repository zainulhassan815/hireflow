# RAG Architecture for HR Screening (Infinity)

## Overview

This document defines the Retrieval-Augmented Generation (RAG) architecture for the HR screening system using **Infinity** as the AI-native database. The goal is to enable natural language queries over resumes and job applications with high-quality retrieval using **hybrid search** and **neural reranking**.

---

## Architecture Evolution

| Version | Database | Search Type | Reranking |
|---------|----------|-------------|-----------|
| v1 (Previous) | PostgreSQL + ChromaDB | Dense vectors only | Manual (external) |
| **v2 (Current)** | **PostgreSQL + Infinity** | **Dense + Sparse + Full-text** | **Built-in (RRF, ColBERT)** |

### Why Infinity?

| Challenge with ChromaDB | Infinity Solution |
|-------------------------|-------------------|
| Dense vectors only | Dense + Sparse + Tensor (ColBERT) |
| No full-text search | Native BM25 with inverted index |
| Manual hybrid search | Single query, fused results |
| External reranking needed | Built-in RRF, weighted sum, ColBERT |
| Separate PostgreSQL filters | Integrated SQL-like filtering |

---

## Query Types

| Query Type | Example | Solution |
|------------|---------|----------|
| Exact lookup | "Ali's resume for SWE job" | PostgreSQL (relational data) |
| Keyword search | "Python React AWS" | Infinity (BM25 full-text) |
| Semantic search | "Candidates with distributed systems experience" | Infinity (dense vectors) |
| Term importance | "Must have Kubernetes certification" | Infinity (sparse vectors) |
| Similarity | "Candidates like this resume" | Infinity (full doc embedding) |
| **Hybrid** | "Senior Python developers with AWS" | **Infinity (3-way + rerank)** |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Query                               │
│            "Find senior Python developers with AWS"              │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Query Processor                               │
│  1. Generate dense embedding (BGE-M3)                           │
│  2. Generate sparse embedding (BGE-M3)                          │
│  3. Extract keywords for BM25                                    │
│  4. Parse structured filters (years_exp >= 5)                   │
└─────────────────────────────┬───────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Infinity Database                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Three-Way Retrieval                    │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │    │
│  │  │  BM25    │  │  Dense   │  │  Sparse  │              │    │
│  │  │ Full-text│  │  Vector  │  │  Vector  │              │    │
│  │  │ top-100  │  │  top-100 │  │  top-100 │              │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘              │    │
│  │       └─────────────┼─────────────┘                     │    │
│  │                     ▼                                   │    │
│  │         ┌─────────────────────┐                        │    │
│  │         │   Fusion (RRF or    │                        │    │
│  │         │   Weighted Sum)     │                        │    │
│  │         └──────────┬──────────┘                        │    │
│  │                    ▼                                    │    │
│  │         ┌─────────────────────┐                        │    │
│  │         │  ColBERT Reranking  │                        │    │
│  │         │     (top-100)       │                        │    │
│  │         └──────────┬──────────┘                        │    │
│  │                    ▼                                    │    │
│  │              Final top-10                               │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                                         ▼
┌─────────────────┐                    ┌─────────────────┐
│   PostgreSQL    │◄───── JOIN ───────│  Candidate IDs  │
│ (Relational)    │                    │  from Infinity  │
│                 │                    └─────────────────┘
│ • User accounts │
│ • Jobs          │
│ • Applications  │
│ • Audit logs    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Response Builder                            │
│  Enrich with candidate details, job info, match breakdown        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### PostgreSQL (Relational Data Only)

PostgreSQL stores relational data that requires ACID transactions and complex joins.

```sql
-- Users (system users, not candidates)
users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    name VARCHAR(100),
    role VARCHAR(20),  -- hr_user, hr_manager, admin
    created_at TIMESTAMP
)

-- Jobs
jobs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users,
    title VARCHAR(200),
    description TEXT,
    required_skills TEXT[],
    preferred_skills TEXT[],
    experience_min INT,
    experience_max INT,
    education_level VARCHAR(50),
    status VARCHAR(20),  -- draft, active, closed
    created_at TIMESTAMP
)

-- Applications (links candidates to jobs)
applications (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs,
    candidate_id UUID,  -- References Infinity
    status VARCHAR(20),  -- new, reviewed, shortlisted, rejected
    match_score FLOAT,
    applied_at TIMESTAMP
)

-- Documents (file references)
documents (
    id UUID PRIMARY KEY,
    candidate_id UUID,  -- References Infinity
    file_path VARCHAR(500),
    file_type VARCHAR(10),
    original_filename VARCHAR(255),
    uploaded_at TIMESTAMP
)

-- Activity logs
activity_logs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users,
    action VARCHAR(50),
    entity_type VARCHAR(50),
    entity_id UUID,
    details JSONB,
    created_at TIMESTAMP
)
```

### Infinity (Search & Retrieval)

Infinity stores all searchable content with multiple embedding types.

**Table: `resumes`**

```sql
-- Infinity table schema
CREATE TABLE resumes (
    -- Identifiers
    id VARCHAR PRIMARY KEY,           -- "{candidate_id}_{chunk_type}"
    candidate_id VARCHAR,
    job_id VARCHAR,

    -- Content
    content TEXT,                     -- Raw text for BM25
    chunk_type VARCHAR,               -- "full" | "experience" | "skills" | "education"

    -- Embeddings (BGE-M3)
    dense_embedding VECTOR(1024),     -- Dense semantic embedding
    sparse_embedding SPARSE_VECTOR,   -- Learned sparse (SPLADE-like)
    colbert_tensor TENSOR,            -- Multi-vector for reranking

    -- Structured metadata (for filtering)
    candidate_name VARCHAR,
    skills ARRAY(VARCHAR),
    years_experience INT,
    education_level VARCHAR,

    -- Timestamps
    created_at TIMESTAMP
);

-- Indexes
CREATE INDEX idx_dense ON resumes (dense_embedding) USING HNSW;
CREATE INDEX idx_sparse ON resumes (sparse_embedding);
CREATE INDEX idx_fulltext ON resumes (content) USING FULLTEXT;
CREATE INDEX idx_candidate ON resumes (candidate_id);
CREATE INDEX idx_job ON resumes (job_id);
```

**Table: `job_descriptions`**

```sql
CREATE TABLE job_descriptions (
    id VARCHAR PRIMARY KEY,
    job_id VARCHAR,

    content TEXT,
    dense_embedding VECTOR(1024),
    sparse_embedding SPARSE_VECTOR,
    colbert_tensor TENSOR,

    required_skills ARRAY(VARCHAR),

    created_at TIMESTAMP
);
```

---

## Embedding Strategy: BGE-M3

### Why BGE-M3?

BGE-M3 generates **three embedding types** in a single forward pass:

| Embedding Type | Purpose | Dimension |
|----------------|---------|-----------|
| **Dense** | Semantic similarity | 1024 |
| **Sparse** | Term importance (like SPLADE) | Variable |
| **ColBERT** | Token-level for reranking | 1024 × num_tokens |

### Implementation

```python
# backend/app/services/embedding.py
from FlagEmbedding import BGEM3FlagModel


class EmbeddingService:
    def __init__(self):
        self.model = BGEM3FlagModel(
            "BAAI/bge-m3",
            use_fp16=True,
            device="cuda"  # or "cpu"
        )

    def embed(self, text: str) -> dict:
        """Generate all three embedding types."""
        output = self.model.encode(
            text,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True
        )
        return {
            "dense": output["dense_vecs"],        # [1024]
            "sparse": output["lexical_weights"],   # {token_id: weight}
            "colbert": output["colbert_vecs"]      # [num_tokens, 1024]
        }

    def embed_batch(self, texts: list[str]) -> list[dict]:
        """Batch embedding for efficiency."""
        output = self.model.encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
            batch_size=32
        )
        return [
            {
                "dense": output["dense_vecs"][i],
                "sparse": output["lexical_weights"][i],
                "colbert": output["colbert_vecs"][i]
            }
            for i in range(len(texts))
        ]
```

### Resource Requirements

| Config | GPU Memory | Throughput |
|--------|------------|------------|
| FP16 + GPU | ~4GB | ~100 docs/sec |
| FP32 + CPU | N/A | ~5 docs/sec |

---

## Chunking Strategy: Hybrid Approach

Same as before, but now with three embedding types per chunk:

```
┌─────────────────────────────────────────────────────────────┐
│                   FULL RESUME                                │
│  id: {candidate_id}_full                                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   Dense     │ │   Sparse    │ │  ColBERT    │           │
│  │   [1024]    │ │ {tok: wt}   │ │ [N, 1024]   │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
                           +
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  EXPERIENCE │ │   SKILLS    │ │  EDUCATION  │ │  PROJECTS   │
│  3 embeds   │ │  3 embeds   │ │  3 embeds   │ │  3 embeds   │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

---

## Indexing Pipeline

```python
# backend/app/services/indexing.py
from infinity import connect


class IndexingService:
    def __init__(self, infinity_url: str):
        self.infinity = connect(infinity_url)
        self.db = self.infinity.get_database("hr_screening")
        self.resumes_table = self.db.get_table("resumes")
        self.embedding_service = EmbeddingService()

    async def index_resume(
        self,
        candidate_id: str,
        job_id: str,
        parsed_resume: ParsedResume
    ) -> None:
        """Index a resume with all embedding types."""

        # 1. Index full resume
        full_embeddings = self.embedding_service.embed(parsed_resume.full_text)

        self.resumes_table.insert({
            "id": f"{candidate_id}_full",
            "candidate_id": candidate_id,
            "job_id": job_id,
            "content": parsed_resume.full_text,
            "chunk_type": "full",
            "dense_embedding": full_embeddings["dense"],
            "sparse_embedding": full_embeddings["sparse"],
            "colbert_tensor": full_embeddings["colbert"],
            "candidate_name": parsed_resume.metadata.name,
            "skills": parsed_resume.metadata.skills,
            "years_experience": parsed_resume.metadata.years_experience,
            "education_level": parsed_resume.metadata.education_level,
        })

        # 2. Index sections
        for section_name, section_text in parsed_resume.sections.items():
            if section_text and len(section_text.strip()) > 50:
                section_embeddings = self.embedding_service.embed(section_text)

                self.resumes_table.insert({
                    "id": f"{candidate_id}_{section_name}",
                    "candidate_id": candidate_id,
                    "job_id": job_id,
                    "content": section_text,
                    "chunk_type": section_name,
                    "dense_embedding": section_embeddings["dense"],
                    "sparse_embedding": section_embeddings["sparse"],
                    "colbert_tensor": section_embeddings["colbert"],
                    "candidate_name": parsed_resume.metadata.name,
                    "skills": parsed_resume.metadata.skills,
                    "years_experience": parsed_resume.metadata.years_experience,
                    "education_level": parsed_resume.metadata.education_level,
                })
```

---

## Search Pipeline

### Three-Way Hybrid Search with Reranking

```python
# backend/app/services/search.py
from infinity import connect
from dataclasses import dataclass


@dataclass
class SearchConfig:
    # Retrieval counts
    bm25_topk: int = 100
    dense_topk: int = 100
    sparse_topk: int = 100
    rerank_topk: int = 100
    final_topk: int = 10

    # Fusion method: "rrf" or "weighted_sum"
    fusion_method: str = "weighted_sum"

    # Weights for weighted_sum fusion
    dense_weight: float = 0.2
    sparse_weight: float = 0.5
    bm25_weight: float = 0.3


class SearchService:
    def __init__(self, infinity_url: str):
        self.infinity = connect(infinity_url)
        self.db = self.infinity.get_database("hr_screening")
        self.resumes_table = self.db.get_table("resumes")
        self.embedding_service = EmbeddingService()
        self.config = SearchConfig()

    async def search(
        self,
        query: str,
        job_id: str | None = None,
        chunk_type: str = "full",
        filters: dict | None = None,
        config: SearchConfig | None = None
    ) -> list[SearchResult]:
        """
        Execute three-way hybrid search with ColBERT reranking.

        This implements the optimal retrieval strategy from Infinity benchmarks:
        BM25 + Dense + Sparse → Fusion → ColBERT Rerank
        """
        cfg = config or self.config

        # Generate query embeddings
        query_embeddings = self.embedding_service.embed(query)

        # Build base query with filters
        base_query = self.resumes_table.query()

        if job_id:
            base_query = base_query.filter(f"job_id = '{job_id}'")

        if chunk_type:
            base_query = base_query.filter(f"chunk_type = '{chunk_type}'")

        if filters:
            for key, value in filters.items():
                if key == "min_experience":
                    base_query = base_query.filter(f"years_experience >= {value}")
                elif key == "skills":
                    # Array contains filter
                    for skill in value:
                        base_query = base_query.filter(f"'{skill}' = ANY(skills)")

        # Three-way retrieval + fusion + reranking
        results = (
            base_query
            # 1. BM25 full-text search
            .match_text("content", query, topn=cfg.bm25_topk)
            # 2. Dense vector search
            .match_dense(
                "dense_embedding",
                query_embeddings["dense"],
                topn=cfg.dense_topk,
                metric="cosine"
            )
            # 3. Sparse vector search
            .match_sparse(
                "sparse_embedding",
                query_embeddings["sparse"],
                topn=cfg.sparse_topk
            )
            # 4. Fusion
            .fusion(
                cfg.fusion_method,
                weights={
                    "dense": cfg.dense_weight,
                    "sparse": cfg.sparse_weight,
                    "bm25": cfg.bm25_weight
                } if cfg.fusion_method == "weighted_sum" else None
            )
            # 5. ColBERT reranking
            .match_tensor(
                "colbert_tensor",
                query_embeddings["colbert"],
                topn=cfg.final_topk
            )
            .to_df()
        )

        return [
            SearchResult(
                candidate_id=row["candidate_id"],
                chunk_type=row["chunk_type"],
                content=row["content"],
                score=row["_score"],
                candidate_name=row["candidate_name"],
                skills=row["skills"],
            )
            for row in results.iter_rows(named=True)
        ]

    async def find_similar_candidates(
        self,
        reference_candidate_id: str,
        job_id: str | None = None,
        topk: int = 10
    ) -> list[SearchResult]:
        """Find candidates similar to a reference candidate."""

        # Get reference embeddings
        reference = self.resumes_table.get(f"{reference_candidate_id}_full")

        query = self.resumes_table.query()

        if job_id:
            query = query.filter(f"job_id = '{job_id}'")

        query = query.filter(f"chunk_type = 'full'")
        query = query.filter(f"candidate_id != '{reference_candidate_id}'")

        results = (
            query
            .match_dense(
                "dense_embedding",
                reference["dense_embedding"],
                topn=100
            )
            .match_sparse(
                "sparse_embedding",
                reference["sparse_embedding"],
                topn=100
            )
            .fusion("rrf")
            .match_tensor(
                "colbert_tensor",
                reference["colbert_tensor"],
                topn=topk
            )
            .to_df()
        )

        return self._to_search_results(results)
```

---

## Candidate-Job Matching

```python
# backend/app/services/matching.py

class MatchingService:
    def __init__(self, search_service: SearchService):
        self.search = search_service

    async def match_candidates_to_job(
        self,
        job_id: str,
        limit: int = 50
    ) -> list[MatchResult]:
        """
        Match all candidates for a job using the job description
        as the query.
        """
        # Get job description embeddings from job_descriptions table
        job_desc = self.search.db.get_table("job_descriptions").get(job_id)

        # Search using job description as query
        results = (
            self.search.resumes_table.query()
            .filter(f"job_id = '{job_id}'")
            .filter("chunk_type = 'full'")
            .match_dense(
                "dense_embedding",
                job_desc["dense_embedding"],
                topn=200
            )
            .match_sparse(
                "sparse_embedding",
                job_desc["sparse_embedding"],
                topn=200
            )
            .fusion("weighted_sum", weights={"dense": 0.3, "sparse": 0.7})
            .match_tensor(
                "colbert_tensor",
                job_desc["colbert_tensor"],
                topn=limit
            )
            .to_df()
        )

        return [
            MatchResult(
                candidate_id=row["candidate_id"],
                match_score=row["_score"],
                candidate_name=row["candidate_name"],
                skills=row["skills"],
                years_experience=row["years_experience"],
            )
            for row in results.iter_rows(named=True)
        ]

    async def explain_match(
        self,
        candidate_id: str,
        job_id: str
    ) -> MatchExplanation:
        """
        Generate detailed match breakdown showing why
        a candidate matches (or doesn't match) a job.
        """
        candidate = self.search.resumes_table.get(f"{candidate_id}_full")
        job = self.search.db.get_table("job_descriptions").get(job_id)

        # Individual scores
        dense_score = cosine_similarity(
            candidate["dense_embedding"],
            job["dense_embedding"]
        )

        sparse_score = sparse_dot_product(
            candidate["sparse_embedding"],
            job["sparse_embedding"]
        )

        colbert_score = colbert_maxsim(
            candidate["colbert_tensor"],
            job["colbert_tensor"]
        )

        # Skill overlap
        candidate_skills = set(candidate["skills"])
        required_skills = set(job["required_skills"])
        skill_match = len(candidate_skills & required_skills) / len(required_skills)

        return MatchExplanation(
            overall_score=(dense_score * 0.2 + sparse_score * 0.5 + colbert_score * 0.3),
            dense_score=dense_score,
            sparse_score=sparse_score,
            colbert_score=colbert_score,
            skill_match_ratio=skill_match,
            matching_skills=list(candidate_skills & required_skills),
            missing_skills=list(required_skills - candidate_skills),
        )
```

---

## Query Examples

### Example 1: Semantic Search with Filters

**Query**: "Find senior Python developers with AWS experience"

```python
results = await search_service.search(
    query="Python developer AWS cloud infrastructure",
    filters={"min_experience": 5},
    config=SearchConfig(
        fusion_method="weighted_sum",
        dense_weight=0.2,
        sparse_weight=0.5,
        bm25_weight=0.3
    )
)
```

**Execution**:
1. BM25 matches: "Python", "developer", "AWS", "cloud", "infrastructure"
2. Dense matches: semantic similarity to the query
3. Sparse matches: term importance weighting
4. Fusion: weighted combination (20% dense, 50% sparse, 30% BM25)
5. ColBERT rerank: token-level cross-attention scoring
6. Filter: `years_experience >= 5`

### Example 2: Skill-Specific Search

**Query**: "React TypeScript frontend experience"

```python
results = await search_service.search(
    query="React TypeScript frontend development",
    chunk_type="skills",  # Search skills sections only
)
```

### Example 3: Similar Candidates

**Query**: "Find candidates similar to candidate #abc123"

```python
results = await search_service.find_similar_candidates(
    reference_candidate_id="abc123",
    job_id="job456",
    topk=10
)
```

### Example 4: Job Matching

**Query**: "Rank all candidates for Software Engineer job"

```python
results = await matching_service.match_candidates_to_job(
    job_id="job456",
    limit=50
)

# Get detailed explanation for top candidate
explanation = await matching_service.explain_match(
    candidate_id=results[0].candidate_id,
    job_id="job456"
)
```

---

## Fusion Strategy Guidelines

Based on [Infinity's benchmark evaluations](https://infiniflow.org/blog/multi-way-retrieval-evaluations-on-infinity-database):

| Retrieval Setup | Recommended Fusion | Notes |
|-----------------|-------------------|-------|
| Two-way (dense + sparse) | Weighted Sum (20/80) | Sparse dominant |
| Three-way (BM25 + dense + sparse) | RRF or Weighted Sum | Similar performance |
| Any + ColBERT rerank | Rerank top 100 | Top 1000 degrades quality |

### Our Configuration

```python
# Optimal for resume search
DEFAULT_CONFIG = SearchConfig(
    bm25_topk=100,
    dense_topk=100,
    sparse_topk=100,
    rerank_topk=100,
    final_topk=10,
    fusion_method="weighted_sum",
    dense_weight=0.2,   # Semantic understanding
    sparse_weight=0.5,  # Term importance (skills, titles)
    bm25_weight=0.3,    # Exact keyword matches
)
```

**Rationale for weights**:
- **Sparse (50%)**: Resume matching is heavily keyword-dependent (skills, job titles, technologies)
- **BM25 (30%)**: Exact matches for certifications, company names, specific terms
- **Dense (20%)**: Semantic similarity for context and related concepts

---

## Performance Expectations

| Operation | Latency | Throughput |
|-----------|---------|------------|
| Single hybrid search | < 50ms | - |
| Batch indexing (100 resumes) | ~10s | 10 docs/sec |
| ColBERT rerank (100 docs) | < 20ms | - |
| Full match ranking (1000 candidates) | < 200ms | - |

---

## Infrastructure

### Docker Compose Addition

```yaml
# docker-compose.yml
services:
  # ... existing services ...

  infinity:
    image: infiniflow/infinity:v0.6
    ports:
      - "23817:23817"  # HTTP API
      - "23818:23818"  # gRPC (optional)
    volumes:
      - infinity_data:/var/infinity
    environment:
      - INFINITY_LOG_LEVEL=info
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:23817/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  infinity_data:
```

### Python Dependencies

```toml
# pyproject.toml additions
[project.dependencies]
infinity-sdk = ">=0.6.0"
FlagEmbedding = ">=1.2.0"
```

---

## Migration from ChromaDB

If migrating from an existing ChromaDB setup:

```python
# scripts/migrate_to_infinity.py

async def migrate_chroma_to_infinity():
    """One-time migration from ChromaDB to Infinity."""

    # Connect to both
    chroma = chromadb.Client()
    infinity = connect("http://localhost:23817")

    collection = chroma.get_collection("resumes")
    infinity_table = infinity.get_database("hr_screening").get_table("resumes")

    # Get all documents from ChromaDB
    all_docs = collection.get(include=["documents", "metadatas", "embeddings"])

    embedding_service = EmbeddingService()

    for i, (doc_id, content, metadata, old_embedding) in enumerate(zip(
        all_docs["ids"],
        all_docs["documents"],
        all_docs["metadatas"],
        all_docs["embeddings"]
    )):
        # Generate new BGE-M3 embeddings
        embeddings = embedding_service.embed(content)

        # Insert into Infinity
        infinity_table.insert({
            "id": doc_id,
            "candidate_id": metadata["candidate_id"],
            "job_id": metadata["job_id"],
            "content": content,
            "chunk_type": metadata.get("type", "full"),
            "dense_embedding": embeddings["dense"],
            "sparse_embedding": embeddings["sparse"],
            "colbert_tensor": embeddings["colbert"],
            "candidate_name": metadata.get("candidate_name"),
            "skills": metadata.get("skills", []),
            "years_experience": metadata.get("years_experience"),
            "education_level": metadata.get("education_level"),
        })

        if i % 100 == 0:
            print(f"Migrated {i} documents")
```

---

## Comparison: Before vs After

| Aspect | ChromaDB (Before) | Infinity (After) |
|--------|-------------------|------------------|
| **Search types** | Dense only | Dense + Sparse + BM25 |
| **Query** | 1 embedding type | 3 embedding types |
| **Fusion** | Manual code | Built-in `.fusion()` |
| **Reranking** | External library | Built-in ColBERT |
| **Full-text** | None | Native BM25 |
| **Filtering** | Metadata only | SQL-like expressions |
| **Result quality** | Single signal | Multi-signal fusion |

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector database | **Infinity** | Native hybrid search, built-in reranking |
| Embedding model | **BGE-M3** | Single model for dense + sparse + ColBERT |
| Chunking strategy | Hybrid (full + sections) | Flexibility for different query types |
| Fusion method | Weighted Sum | Better than RRF for two-way; similar for three-way |
| Fusion weights | 20% dense, 50% sparse, 30% BM25 | Optimized for keyword-heavy resume matching |
| Reranking | ColBERT (top 100) | Significant quality improvement |
| Metadata storage | PostgreSQL | ACID for users, jobs, applications |

---

## Research Status

- [x] Chunking strategy for resumes
- [x] Embedding model selection (BGE-M3)
- [x] **Similarity threshold tuning** → Replaced with fusion + reranking
- [x] **Reranking strategies** → ColBERT built into Infinity

---

## References

- [Infinity Database](https://github.com/infiniflow/infinity)
- [Infinity Documentation](https://infiniflow.org/docs/)
- [AI-Native Database Blog](https://infiniflow.org/blog/ai-native-database)
- [Database for RAG](https://infiniflow.org/blog/database-for-rag)
- [Multi-way Retrieval Evaluations](https://infiniflow.org/blog/multi-way-retrieval-evaluations-on-infinity-database)
- [BGE-M3 Model](https://huggingface.co/BAAI/bge-m3)
- [FlagEmbedding Library](https://github.com/FlagOpen/FlagEmbedding)
