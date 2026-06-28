# VC Due Diligence System — Merger Report
**Prepared by Ujwal Sanikam**
**Date: June 25, 2026**

---

## What This Document Covers

This document explains everything that was done to merge our three individual codebases into one working system. It covers the architecture decisions, every file in the merged project, what each file does, what was changed from the originals, and how to run the full pipeline end-to-end. Read this before touching any code.

---

## Project Overview

We built a Multi-Hop VC Due Diligence System that takes three inputs — a startup pitch deck PDF, a GitHub codebase, and patent documents — and automatically generates adversarial due diligence questions for venture capital investors. The system reasons across all three domains simultaneously using a knowledge graph and multi-hop BFS traversal, then uses a local LLM (phi3 via Ollama) to generate the final questions with full audit trails.

The system successfully runs end-to-end in approximately 90 seconds on a standard laptop (i5, 16GB RAM, no GPU) and generates questions like:

> *"Given the similarity score of 0.42 between your software's use of 'collections' and patent claim context related to an 'encrypted ledger', can you provide detailed documentation proving there is no infringement on patent rights associated with this library?"*

Each question comes with a complete audit trail showing the exact reasoning path: `Claim → Library → Patent Concept`.

---

## Final Folder Structure

```
vc_due_diligence/
│
├── data/
│   ├── raw/
│   │   ├── patents/              ← patent .txt files go here
│   │   ├── pitch_decks/          ← startup PDF goes here
│   │   └── repositories/         ← cloned startup repo goes here
│   └── processed/                ← all JSON outputs land here
│
├── src/
│   ├── extractors/
│   │   ├── whitepaper_parser.py  ← Samhitha
│   │   ├── github_parser.py      ← Samhitha
│   │   └── patent_parser.py      ← Samhitha
│   │
│   ├── parsers/
│   │   └── license_parser.py     ← Ujwal
│   │
│   ├── graph/
│   │   ├── knowledge_fusion.py   ← MERGED (Ujwal + Samhitha)
│   │   └── kg_builder.py         ← Vaibhav
│   │
│   ├── resolvers/
│   │   └── entity_resolver.py    ← Vaibhav
│   │
│   ├── reasoning/
│   │   ├── contradiction_detector.py  ← Ujwal (updated)
│   │   ├── hop_reasoner.py            ← Vaibhav (threshold fixed)
│   │   └── mhqg_engine.py             ← Samhitha (fallback)
│   │
│   ├── scoring/
│   │   ├── confidence_engine.py  ← Ujwal
│   │   └── legal_analyzer.py     ← Samhitha
│   │
│   ├── audit/
│   │   └── explainability_engine.py  ← Ujwal (new)
│   │
│   ├── generation/
│   │   └── question_gen.py       ← Vaibhav (updated for Ollama)
│   │
│   └── pipeline.py               ← Ujwal (orchestrator, updated)
│
├── scripts/
│   └── patent_downloader.py      ← Vaibhav
│
├── tests/
├── requirements.txt              ← merged from all three
├── README.md
└── debug_scores.py               ← diagnostic tool (can delete after testing)
```

---

## Architecture

The system runs in 10 sequential stages orchestrated by `pipeline.py`:

```
PDF / GitHub Repo / Patent .txt files
           │
    ┌──────┴──────┐
    ▼             ▼             ▼
Stage 1        Stage 2       Stage 3
whitepaper_    github_       patent_
parser.py      parser.py     parser.py
    │             │             │
    └──────┬───────┘─────────────┘
           ▼
        Stage 4
   knowledge_fusion.py
   (MERGED — builds dual-label
    knowledge graph with FAISS
    semantic bridging)
           │
           ▼
        Stage 5
   entity_resolver.py
   (cross-domain FAISS matching)
           │
           ▼
        Stage 6
    kg_builder.py
    (typed KG with node/edge taxonomy)
           │
     ┌─────┴──────┐
     ▼            ▼
  Stage 7      Stage 8
contradiction  hop_reasoner.py
_detector.py   (BFS traversal,
(keyword +     chain scoring)
 semantic)
               │
               ▼
            Stage 9
         question_gen.py
         (Ollama phi3 primary,
          mhqg_engine fallback)
               │
               ▼
            Stage 10
     explainability_engine.py
     (SHA-256 audit trail)
               │
               ▼
     audited_vc_report.json
```

### Graph Schema

Every node in the knowledge graph carries **both** label systems so all downstream files work without edits:

| label (Samhitha schema) | node_type (Vaibhav schema) | Source |
|---|---|---|
| `Marketing_Claim` | `Claim` | whitepaper_parser.py |
| `Software_Dependency` | `Library` | github_parser.py |
| `Patent_Concept` | `Patent` | patent_parser.py |
| `OpenSource_License` | `LicenceType` | license_parser.py |
| `Code_Module` | `Library` | github_parser.py (import graph) |

### Bridge Layers

The knowledge fusion stage adds three types of semantic edges:

| Layer | Direction | Edge Type | Method |
|---|---|---|---|
| 1 | Claim → Dependency | `IMPLEMENTED_BY` | FAISS cosine similarity |
| 2 | Dependency → Patent | `SIMILAR_TO` | FAISS cosine similarity |
| 3 | Code Module → Patent | `REQUIRES_IP_REVIEW` | FAISS cosine similarity |

---

## File-by-File Breakdown

### `src/extractors/whitepaper_parser.py` — Samhitha, unchanged
Extracts technical claims from startup pitch deck PDFs. Uses three-tier extraction: pdfplumber (primary) → pypdf (fallback) → Tesseract OCR (scanned docs). Detects claims across 5 categories (security, performance, architecture, protocol, data), resolves buzzwords (e.g. "military-grade" → "AES-256"), and extracts numeric assertions (TPS, latency). Outputs `*_parsed.json`.

### `src/extractors/github_parser.py` — Samhitha, unchanged
Analyzes startup codebase in two modes. Mode A: parses dependency manifests (`requirements.txt`, `pyproject.toml`, `package.json`, `Pipfile`). Mode B: builds AST-based import graph using NetworkX. Detects hub modules, orphan files, circular imports. Outputs `dependency_map.json` and `codebase_knowledge.json`.

### `src/extractors/patent_parser.py` — Samhitha, unchanged
Converts patent text into structured triples (`head → relationship → tail`). Integrates with USPTO PatentsView API with retry logic. Infers patent status from grant date (20-year expiry rule). Outputs `knowledge_base.json`.

### `src/parsers/license_parser.py` — Ujwal, unchanged
Track 4 input. Parses open-source license data and classifies commercial-use risk. Adds `OpenSource_License` / `LicenceType` nodes to the graph. Outputs `license_knowledge.json`. Optional — pipeline skips gracefully if file is missing.

### `src/graph/knowledge_fusion.py` — MERGED (Ujwal + Samhitha)
**This is the most important merged file.** Combines Ujwal's `SemanticFusionPipeline` and Samhitha's `KnowledgeFusionPipeline` into one `KnowledgeFusionPipeline` class.

Key changes made during merger:
- Every node now carries both `label` AND `node_type` attributes (dual-label system) so `mhqg_engine.py`, `hop_reasoner.py`, and `contradiction_detector.py` all work without edits
- FAISS `IndexFlatIP` replaces the O(n²) numpy cosine loop — faster on large graphs
- Added `_DEP_ENRICHMENT` dictionary: bare library names like `"hashlib"` become `"hashlib cryptographic hashing security"` so the embedding model can match them semantically against claim text
- Loads both `dependency_map.json` (Samhitha's flat list) AND `codebase_knowledge.json` import graph (Ujwal's format) — deduplicates by node ID
- Pitch deck loader is now filename-agnostic (globs `*_parsed.json`) instead of hardcoding `expense_ninja_pitch_parsed.json`
- EXPIRED patents excluded from bridge layers (no false risk signals)
- Dual JSON export: both `"links"` key (used by `mhqg_engine.py`) and `"edges"` key (used by `hop_reasoner.py`) in the same file
- GraphML export with None-value fix (NetworkX crashes on None attributes)
- Configurable threshold via `--threshold` CLI flag (default 0.40; use 0.15 for sparse data)

### `src/graph/kg_builder.py` — Vaibhav, unchanged
Builds the typed knowledge graph consumed by `hop_reasoner.py`. Reads `fused_knowledge_graph.json` and produces `kg.json` with Vaibhav's node/edge taxonomy (4 node types, 6 edge types). Also produces `kg_summary.json` with high-risk library flagging.

### `src/resolvers/entity_resolver.py` — Vaibhav, one fix
Cross-domain FAISS matching with enriched embedding strings, symmetric deduplication, and provenance ledger. **Fixed:** `SCORE_THRESH` lowered from `0.78` to `0.45` — the original threshold was too aggressive and produced 0 matches in testing.

### `src/reasoning/contradiction_detector.py` — Ujwal, updated
Keyword-based engine that catches direct claim-vs-code mismatches (e.g. startup claims "proprietary authentication" but codebase imports `flask_login`). **Updated during merger:** now imports and calls `ConfidenceEngine` from `scoring/confidence_engine.py` instead of hardcoding `confidence_score: 0.99`. Also fixed a double-path bug where output was writing to `data/processed/processed/` instead of `data/processed/`.

### `src/reasoning/hop_reasoner.py` — Vaibhav, one fix
BFS traversal over the knowledge graph starting from every Claim node. Scores chains using geometric mean of edge weights with length penalty. Classifies chains by licence conflict and patent presence. Outputs `hop_chains.json` with full provenance per chain. **Fixed:** `CHAIN_THRESHOLD` lowered from `0.82` to `0.28` — the original threshold killed every chain since edge weights from the fusion layer average 0.35–0.45.

### `src/reasoning/mhqg_engine.py` — Samhitha, unchanged (fallback)
Template-based question generation as fallback when no LLM API key is set. Uses 3-hop graph traversal (Claim → IMPLEMENTED_BY → Dependency → SIMILAR_TO → Patent Concept). Includes Levenshtein-ratio deduplication and `--min-risk` filter. Used automatically by `pipeline.py` when `ANTHROPIC_API_KEY` is not set and Ollama is unavailable.

### `src/scoring/confidence_engine.py` — Ujwal, unchanged
Centralized mathematical engine for risk scoring. Calculates final confidence based on edge weights with hop-length decay (10% penalty per hop beyond the first). Maps scores to severity levels: CRITICAL (≥0.85), HIGH (≥0.65), MODERATE (≥0.40), LOW (<0.40). Commercial licence violations are always CRITICAL if confirmed. Now correctly imported by `contradiction_detector.py`.

### `src/scoring/legal_analyzer.py` — Samhitha, unchanged
Weighted IP risk scoring: active patent status (+0.40), commercial restriction (+0.30), US jurisdiction (+0.20), known competitor assignee (+0.10). EXPIRED and PENDING patents short-circuit to risk=0. EU/UK jurisdiction scored at 60% of US weight.

### `src/audit/explainability_engine.py` — Ujwal, new file
Generates SHA-256-based trace IDs for every question in the output. Reads `questions.json`, wraps each item with a `TRC-XXXXXXXXXXXX-timestamp` identifier, and writes `audited_vc_report.json`. Format: `TRC-{first 12 chars of SHA-256 hash of provenance + question}-{unix timestamp}`. Status field: `MACHINE_ASSISTED_VERIFICATION`.

### `src/generation/question_gen.py` — Vaibhav, updated for Ollama
Primary question generator. **Updated during merger** to support Ollama as the default LLM backend (no API key needed) with Anthropic Claude as an optional fallback. Routes to Ollama's local REST API at `localhost:11434`. Checks if Ollama is running and if the requested model is available before calling. Retries 3 times with exponential backoff. Falls back to `mhqg_engine.py` if neither backend is available. Also fixed: `build_chain_summary()` now handles `None` edge weights without crashing.

### `src/pipeline.py` — Ujwal, significantly updated
The main orchestrator. Runs all 10 stages in sequence with timing at each stage. **Key fixes made during merger:**
- Removed bad `from html import parser` import
- `args.backend` and `args.model` now correctly passed to `run_question_gen()` (was missing, causing phi3 to be ignored)
- Dead code and duplicate `except` clause removed from `run_question_gen()`
- Stage numbering corrected (was two "Stage 6" and two "Stage 7")
- `run_explainability_engine()` now actually called in `run_pipeline()` (was defined but never invoked)
- `data_root` derivation moved to top of `run_pipeline()` and used consistently
- Placeholder `codebase_knowledge.json` now includes `import_graph_structure` so downstream stages don't crash when no repo is provided
- Produces timing report, eval results, and outputs paths for all 10 deliverables

---

## Key Merger Decisions

Three architectural decisions were made before any code was written:

**Decision 1 — Dual-label nodes (Option C):** Every graph node carries both `label` (Samhitha's schema) and `node_type` (Vaibhav's schema). This means `mhqg_engine.py`, `hop_reasoner.py`, and `contradiction_detector.py` all read the same graph without any edits to their parsing logic.

**Decision 2 — Single output filename:** The knowledge graph JSON is always named `fused_knowledge_graph.json`. It contains both a `"links"` key (for `mhqg_engine.py` and `contradiction_detector.py`) and an `"edges"` key (for `hop_reasoner.py`) pointing to the same data.

**Decision 3 — LLM backend:** Vaibhav's `question_gen.py` with Ollama as the primary generator (no API key needed). Samhitha's `mhqg_engine.py` as automatic fallback. If `ANTHROPIC_API_KEY` is set and `--backend anthropic` is passed, Claude API is used instead.

---

## Threshold Values (All Fixed)

| Parameter | Original | Fixed | Why |
|---|---|---|---|
| `hop_reasoner.py CHAIN_THRESHOLD` | 0.82 | 0.28 | Edge weights average 0.35–0.45; 0.82 killed every chain |
| `entity_resolver.py SCORE_THRESH` | 0.78 | 0.45 | Produced 0 matches in all tests at 0.78 |
| `knowledge_fusion.py _DEFAULT_THRESHOLD` | 0.35 | 0.40 | Slightly higher precision; tunable via `--fusion-threshold` |
| Pipeline `--fusion-threshold` for sparse data | — | 0.15 | Use this when repo has few or unrelated dependencies |
| Pipeline `--chain-threshold` for sparse data | — | 0.10 | Use this alongside fusion-threshold 0.15 |

---

## What Each Output File Contains

| File | Produced by | Contents |
|---|---|---|
| `*_parsed.json` | whitepaper_parser | Claims, assertions, entities from pitch deck |
| `dependency_map.json` | github_parser | Flat list of all library dependencies |
| `codebase_knowledge.json` | github_parser | Import graph + dependency map combined |
| `knowledge_base.json` | patent_parser | Patent triples (head → rel → tail) |
| `fused_knowledge_graph.json` | knowledge_fusion | Complete dual-label knowledge graph (JSON) |
| `fused_knowledge_graph.graphml` | knowledge_fusion | Same graph in GraphML for Gephi visualisation |
| `entity_matches.json` | entity_resolver | Cross-domain semantic matches with scores |
| `kg.json` | kg_builder | Typed knowledge graph for hop_reasoner |
| `kg_summary.json` | kg_builder | Node/edge counts, high-risk library list |
| `contradiction_evidence.json` | contradiction_detector | Proprietary claim mismatches with confidence |
| `hop_chains.json` | hop_reasoner | Scored reasoning chains with provenance |
| `questions.json` | question_gen | Generated questions with audit trails |
| `audited_vc_report.json` | explainability_engine | Questions wrapped with SHA-256 trace IDs |
| `pipeline_timing.json` | pipeline | Per-stage latency for optimization |
| `eval_results.json` | pipeline | Phase 1 pass/fail and category breakdown |

---

## How to Run

### Setup

```powershell
# Clone the repo
git clone <repo_url>
cd vc_due_diligence

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Install and start Ollama (one time)
# Download from https://ollama.com
ollama pull phi3
```

### Put your data in the right places

```
data/raw/pitch_decks/   ← your startup PDF
data/raw/patents/       ← patent .txt files
data/raw/repositories/  ← git clone the startup's repo here
```

### Run the full pipeline

```powershell
# Standard run (good data — repo has crypto/ML libraries)
python src/pipeline.py --whitepaper data/raw/pitch_decks/startup.pdf --repo data/raw/repositories/startup_repo --patents data/raw/patents --output data/processed/ --max-questions 5 --backend ollama --model phi3

# Sparse data run (repo has unrelated libraries)
python src/pipeline.py --whitepaper data/raw/pitch_decks/startup.pdf --repo data/raw/repositories/startup_repo --patents data/raw/patents --output data/processed/ --max-questions 5 --fusion-threshold 0.15 --chain-threshold 0.10 --backend ollama --model phi3

# Dry run (no LLM call — just test the pipeline)
python src/pipeline.py --whitepaper data/raw/pitch_decks/startup.pdf --repo data/raw/repositories/startup_repo --patents data/raw/patents --output data/processed/ --dry-run --max-questions 3
```

### For the best demo results

Clone Vaibhav's repo as the target codebase — it has `cryptography`, `hashlib`, `faiss`, `sentence-transformers` which directly match the crypto claim in the pitch deck:

```powershell
cd data/raw/repositories
git clone https://github.com/Vaibhav-alt0246/MULTI_HOP_VC

python src/pipeline.py --whitepaper data/raw/pitch_decks/expense_ninja_pitch.pdf --repo data/raw/repositories/MULTI_HOP_VC --patents data/raw/patents --output data/processed/ --max-questions 5 --backend ollama --model phi3
```

---

## Confirmed Working Output (June 25, 2026)

Running with `expense_ninja_pitch.pdf` + Samhitha's CCBD repo + `patent_mock.txt`:

```
Bridge Layer1 (Claim→Dep): 3 IMPLEMENTED_BY edges
Bridge Layer2 (Dep→Patent): 72 SIMILAR_TO edges  
Bridge Layer3 (Module→Patent): 68 REQUIRES_IP_REVIEW edges
Hop reasoning: 5 chains (3 with patent nodes)
Questions generated: 3
Phase 1 check: PASS
Total runtime: ~94 seconds
```

Sample question generated:

> **[IP_CONFLICT] [PATENT]** — *"Given the similarity score of 0.42 between your software's use of 'collections' and patent claim context related to an 'encrypted ledger', can you provide detailed documentation or source code excerpts proving that there is no infringement on patent rights associated with this library?"*

Audit trail: `claim_0001 → collections → database → encrypted ledger`

---

## Known Limitations and Notes

The test data (Samhitha's CCBD repo) only has 5 lightweight dependencies (`pypdf`, `networkx`, `pydantic`, `python-dotenv`, `pytest`) which don't semantically match the crypto claim in the pitch deck. This is why `--fusion-threshold 0.15` is needed for this specific combination. Using Vaibhav's repo or a repo with actual crypto libraries will work at the default 0.40 threshold.

The sentence-transformer model (`all-MiniLM-L6-v2`) is downloaded from HuggingFace on first run. After the first run it is cached locally and subsequent runs are much faster (model load drops from ~30s to ~6s).

The FAISS AVX512/AVX2 warnings at startup are harmless — it falls back to the standard CPU implementation automatically.

Question generation with phi3 on CPU takes approximately 20–25 seconds per question. This is normal for CPU inference. For a live demo, run the pipeline beforehand and show the output files.

---

## Repos

| Teammate | Repo |
|---|---|
| Ujwal (you) | https://github.com/UjwalSanikam/ccbd_local |
| Vaibhav | https://github.com/Vaibhav-alt0246/MULTI_HOP_VC |
| Samhitha | https://github.com/Samhithakanth/CCBD |

---

*Built by Ujwal Sanikam, Vaibhav, and Samhitha Kanth — June 2026*
