# ChainCheck — VC Technical and Legal Risk Interrogator
### Multi-Hop Reasoning System for Venture Capital Technical Due Diligence
**Team:** Vaibhava L (CS512) · Ujwal Sanikam L (CS506) · Samhitha Kanth (AM245)  
**Team Name:** ChainCheck

---

## Table of Contents
1. [What This Project Does](#1-what-this-project-does)
2. [Why It Exists — The Problem](#2-why-it-exists--the-problem)
3. [The Core Idea — Multi-Hop Reasoning](#3-the-core-idea--multi-hop-reasoning)
4. [System Architecture Overview](#4-system-architecture-overview)
5. [Data Inputs](#5-data-inputs)
6. [Every Python File Explained](#6-every-python-file-explained)
7. [The 10-Stage Pipeline In Detail](#7-the-10-stage-pipeline-in-detail)
8. [What the Output Looks Like](#8-what-the-output-looks-like)
9. [Key Technical Decisions](#9-key-technical-decisions)
10. [Known Limitations](#10-known-limitations)
11. [How To Run](#11-how-to-run)

---

## 1. What This Project Does

ChainCheck is an automated technical due diligence system for venture capital investors. Given three inputs — a startup's pitch deck PDF, their GitHub codebase, and a set of patent files — it automatically:

1. Extracts claims the startup makes about their technology
2. Maps those claims against what their codebase actually uses
3. Connects those dependencies to relevant patents
4. Detects contradictions between what the startup claims and what the code shows
5. Generates pointed, adversarial due diligence questions that a VC investor should ask the founder

The system runs end-to-end in approximately 3–4 minutes on a standard laptop CPU with no GPU required and no paid API keys needed (uses a local Ollama LLM).

---

## 2. Why It Exists — The Problem

Venture capital firms evaluating startups face three specific problems during technical due diligence:

**Vocabulary mismatch.** A pitch deck says "proprietary military-grade cryptographic hashing module." The codebase says `import hashlib`. A patent says "cryptographic hash function with salted digest chaining." These three phrases describe overlapping concepts but share almost no words, making automated cross-referencing extremely hard.

**Data silos.** The relevant information is spread across completely incompatible formats: unstructured PDF text (pitch decks), structured dependency graphs (GitHub repos), and dense legal prose (patents). No existing tool connects all three.

**Hallucination risk.** A standard LLM asked "does this startup infringe Patent X?" will confidently answer yes or no with no traceable evidence. In a VC deal worth millions, a false IP accusation is catastrophic.

ChainCheck solves all three: it uses semantic embedding to bridge vocabulary gaps, builds a unified knowledge graph to break down data silos, and generates SHA-256 cryptographic audit trails so every output is traceable to its exact evidence.

---

## 3. The Core Idea — Multi-Hop Reasoning

The system's key insight is that risk evidence is never a single fact — it's a chain of connected facts across domains. The chain looks like this:

```
Claim (pitch deck) → Library (codebase) → Patent (USPTO)
         ↓                    ↓                  ↓
"proprietary          imports hashlib      Patent US10831908B2
 hashing module"                           (IBM, Active 2020)
         └──────────────────────────────────────┘
                         generates:
   "Your whitepaper claims a proprietary hashing module, 
    but the codebase calls Python's standard hashlib — 
    what specifically have you built on top of hashlib 
    that justifies calling it proprietary, and can you 
    show us the diff?"
```

This is called a 3-hop chain: it hops from a Claim node, to a Library node, to a Patent node. Each hop is a semantically scored edge in a knowledge graph. The system uses BFS (breadth-first search) to discover all valid chains, scores them using geometric mean of edge weights with a length penalty, and feeds the top chains to the LLM for question generation.

---

## 4. System Architecture Overview

The pipeline has 10 sequential stages divided into two layers:

```
INPUT SOURCES
─────────────────────────────────────────────────────────
  Pitch deck PDF          GitHub Codebase     Patent .txt files
  whitepaper_parser.py    github_parser.py    patent_parser.py
─────────────────────────────────────────────────────────
                              ↓
CLOUD & BIG DATA LAYER
─────────────────────────────────────────────────────────
  Stage 4: Knowledge Fusion
  knowledge_fusion.py — Dual-label KG — 3-layer FAISS semantic bridging
  Claim→[IMPLEMENTED_BY]→Library→[SIMILAR_TO]→Patent
  Module→[REQUIRES_IP_REVIEW]→Patent
─────────────────────────────────────────────────────────
  Stage 5: Entity Resolver
  entity_resolver.py — cross-domain FAISS matching — threshold 0.45
─────────────────────────────────────────────────────────
  Stage 6: KG Builder
  kg_builder.py — typed knowledge graph
─────────────────────────────────────────────────────────
              ↓                           ↓
NLP / REASONING LAYER
┌─────────────────────────┐   ┌─────────────────────────┐
│  Stage 7                │   │  Stage 8                │
│  Contradiction Detector │   │  Hop Reasoner           │
│  contradiction_         │   │  hop_reasoner.py        │
│  detector.py            │   │  BFS · 3 hops           │
│  keyword taxonomy +     │   │  chain threshold 0.28   │
│  confidence_engine.py   │   │                         │
└─────────────────────────┘   └─────────────────────────┘
              ↓                           ↓
─────────────────────────────────────────────────────────
  Stage 9: Question Generation
  question_gen.py — Ollama phi3 (local) — fallback: mhqg_engine.py
─────────────────────────────────────────────────────────
  Stage 10: Explainability Engine
  explainability_engine.py — SHA-256 trace IDs — audit trail
─────────────────────────────────────────────────────────
                              ↓
OUTPUT: audited_vc_report.json
```

---

## 5. Data Inputs

### Pitch Deck: `data/raw/pitch_decks/vaultchain_pitch.pdf`
A 1-page PDF for a fictional fintech startup called VaultChain Technologies. Contains 4 specific technical claims designed to trigger 3-hop chains:

- **Claim 1:** "Our platform uses a proprietary, military-grade cryptographic hashing module to secure user transaction ledgers locally without relying on open-source authentication."
- **Claim 2:** "Our custom ECDSA signature verification engine is built entirely in-house and does not depend on any third-party cryptographic libraries."
- **Claim 3:** "VaultChain's authentication layer uses a novel password-based key derivation system that is proprietary and patent-pending."
- **Claim 4:** "The distributed hash chain linking algorithm is our core patented IP and forms the basis of our defensible moat."

### GitHub Repo: `data/raw/repositories/cryptosecure_startup/`
A clone of `github.com/warner/python-ecdsa` — a real open-source ECDSA library. Its `requirements.txt` has been augmented with: `six`, `cryptography`, `pycryptodome`, `passlib`, `hashlib2`, `ecdsa`, `bcrypt`, `pyotp`. These deps directly contradict Claim 2 (which says no third-party crypto libraries are used).

### Patents: `data/raw/patents/`
Five real and semi-synthetic patent files:
- `patent_CN110138567B.txt` — ECDSA collaborative signing (Guangzhou Anyan, 2021) — matches `ecdsa` dep
- `patent_US11757625B2.txt` — Multi-factor PKI private key distribution (Mine Zero GmbH, 2023) — matches `cryptography`, PBKDF2
- `patent_US12355864B1.txt` — Cryptographic hash trust framework (Amazon, 2025) — matches `hashlib`
- `patent_US10831908B2.txt` — SHA-256 hash acceleration and ledger integrity (IBM, 2020) — matches `hashlib`, `digest chaining`
- `patent_US11463258B1.txt` — PBKDF2 multi-factor key derivation (RSA Security, 2022) — matches `cryptography`, `passlib`, `bcrypt`

---

## 6. Every Python File Explained

### `src/pipeline.py`
**Owner:** Integration (all three teammates)  
**What it does:** The master orchestrator. Runs all 10 stages in sequence, passes outputs between stages as file paths, tracks timing per stage, and prints a final timing report and evaluation summary. Accepts CLI arguments for all tunable parameters.

**Key functions:**
- `run_pipeline(args)` — main entry point, runs all 10 stages in order
- `run_whitepaper_parser()` — calls Stage 1
- `run_github_parser()` — calls Stage 2, also writes `dependency_map.json` separately so knowledge_fusion.py can load named deps
- `run_knowledge_fusion()` — calls Stage 4 with `data_root` path
- `StageTimer` class — tracks latency per stage, identifies the bottleneck

**Critical fix applied:** Added explicit `dependency_map.json` write after Stage 2 so Bridge Layer 2 in knowledge_fusion.py receives `Software_Dependency` typed nodes rather than falling back to `Code_Module` typed nodes from the import graph.

---

### `src/extractors/whitepaper_parser.py`
**Owner:** Samhitha  
**What it does:** Parses a startup pitch deck PDF and extracts structured technical claims. Uses `pdfplumber` as the primary parser with `pypdf` as fallback. Applies regex and NLP heuristics to identify sentences that are technical claims vs general marketing statements.

**Output:** `data/processed/vaultchain_pitch_parsed.json`  
**Key fields in output:** `technical_claims` (list of claim objects with `claim_id`, `sentence`, `page`, `confidence`, `claim_type`), `statistics` (counts of claims, assertions, entities)  
**Current output:** 10 claims, 1 assertion, 3 entities extracted from 1-page PDF

---

### `src/extractors/github_parser.py`
**Owner:** Samhitha  
**What it does:** Two complementary modes run simultaneously:

- **Mode A (Dependency Mapper):** Parses `requirements.txt`, `package.json`, `pyproject.toml`, `Pipfile` to extract all external library dependencies with name, version spec, ecosystem (PyPI/npm), and category (Security/Crypto, ML/AI, Database, etc.)
- **Mode B (Import Graph Analyzer):** Walks all `.py` files using Python's `ast` module, extracts every `import` and `from X import Y` statement, builds a directed NetworkX graph of module dependencies, identifies hub modules, orphan files, and circular dependency risks.

**Output files:** `codebase_knowledge.json` (combined), `dependency_map.json` (flat dep list written by pipeline.py)  
**Current output:** 8 deps from `requirements.txt`, 85 import graph nodes, 230 import edges, 0 cycles  
**Key fix note:** `hashlib` is in `_STDLIB_MODULES` so it never appears in `requirements.txt` parse output — it only appears as an import graph node.

---

### `src/extractors/patent_parser.py`
**Owner:** Samhitha  
**What it does:** Reads patent `.txt` files and extracts structured knowledge triples in `{head :: relationship :: tail}` format. Uses sentence tokenization and LLM-assisted extraction to identify the key claims and relationships in patent text. Adds legal metadata (status, assignee, jurisdiction, legal_risk_flag) via synthetic benchmark since full USPTO API integration is pending.

**Output:** Individual `patent_XXXX_triples.json` files + combined `knowledge_base.json`  
**Current output:** 6 triples total across 5 patents  
**Critical issue:** The synthetic benchmark marks all patents with `legal_risk_flag: false`, which was causing Bridge Layer 2 to filter out all patent nodes. Fixed by removing the `legal_risk_flag` filter from `bridge_dependencies_to_patents()` in `knowledge_fusion.py`.

---

### `src/graph/knowledge_fusion.py`
**Owner:** Samhitha (core), merged with Vaibhav and Ujwal  
**What it does:** The most architecturally complex file. Builds the unified knowledge graph from all four data tracks and creates semantic bridges between them using FAISS and sentence-transformers.

**Dual-label architecture:** Every node carries two label systems simultaneously:
- `label` (Samhitha/mhqg_engine schema): `Marketing_Claim`, `Software_Dependency`, `Patent_Concept`, `Code_Module`, `OpenSource_License`
- `node_type` (Vaibhav/hop_reasoner schema): `Claim`, `Library`, `Patent`, `Library`, `License`

**Four data tracks:**
- Track 1: Marketing claims from `*_parsed.json`
- Track 2: Dependencies and import graph from `dependency_map.json` + `codebase_knowledge.json`
- Track 3: Patent concept nodes from `knowledge_base.json`
- Track 4: License data from `license_knowledge.json` (optional, skipped if missing)

**Three semantic bridge layers (all use FAISS IndexFlatIP + all-MiniLM-L6-v2):**
- **Bridge Layer 1** (`bridge_claims_to_dependencies`): Scores Marketing_Claim nodes against enriched dep strings using `_DEP_ENRICHMENT` dictionary. Adds `IMPLEMENTED_BY` edges at threshold 0.40. The `_DEP_ENRICHMENT` dict maps dep names like `hashlib` → `"cryptographic hashing security hash digest"` to fix vocabulary mismatch between marketing language and library names.
- **Bridge Layer 2** (`bridge_dependencies_to_patents`): Scores Software_Dependency/Code_Module nodes against Patent_Concept node IDs. Adds `SIMILAR_TO` edges at threshold 0.40.
- **Bridge Layer 3** (`bridge_modules_to_patents`): Ujwal's variant — scores Code_Module nodes against Patent_Concept nodes. Adds `REQUIRES_IP_REVIEW` edges at threshold 0.40.

**Key bug fixed during development:** `load_dependencies` method was defined at module level (missing 4 spaces of indentation) instead of inside the `KnowledgeFusionPipeline` class, causing an `AttributeError` when `fuse_knowledge_domains()` called `self.load_dependencies()`. Fixed by re-indenting lines 219–296.

**Current output:** 113 nodes, 248 edges — breakdown: 230 IMPORTS, 12 IMPLEMENTED_BY, 2 utilizes, 2 stores, 1 generates, 1 secures

---

### `src/resolvers/entity_resolver.py`
**Owner:** Vaibhav  
**What it does:** Cross-domain entity matching using FAISS and sentence-transformers. Separately embeds entities from all three domains (whitepaper, codebase, patents) and finds matches above a similarity threshold of 0.45. Operates on string entities extracted from each parser's output rather than graph nodes.

**Output:** `data/processed/entity_matches.json`  
**Current output:** 6 whitepaper→codebase matches, 28 whitepaper→patent matches, 0 codebase→patent matches, 34 total unique cross-domain matches

---

### `src/graph/kg_builder.py`
**Owner:** Vaibhav  
**What it does:** Loads the fused knowledge graph (preferring `fused_knowledge_graph.json` over `entity_matches.json`) and builds the final typed knowledge graph used by downstream reasoning stages. Identifies high-risk libraries by cross-referencing known vulnerable library lists.

**Output:** Updated graph in memory, passed to hop_reasoner  
**Current output:** 113 nodes, 248 edges, 0 high-risk libs flagged

---

### `src/reasoning/hop_reasoner.py`
**Owner:** Vaibhav  
**What it does:** BFS traversal of the knowledge graph starting from all `Claim` type nodes. Discovers reasoning chains up to 3 hops. Scores each chain using geometric mean of edge weights with a length penalty. Keeps chains above `CHAIN_THRESHOLD = 0.28`. Flags chains that pass through Patent nodes (`has_patent_node = True`) and License nodes (`has_licence_conflict = True`).

**Output:** `data/processed/hop_chains.json`  
**Current output:** 14 chains found, 0 with licence conflict, 0 with patent (when `legal_risk_flag` filter is active) / 3+ with patent (after fix)  
**Scoring formula:** `geometric_mean(edge_weights) × length_penalty` where `length_penalty = 1.0 / (1.0 + 0.1 × hop_count)`

---

### `src/scoring/contradiction_detector.py`
**Owner:** Ujwal  
**What it does:** Keyword-based contradiction detection running in parallel with semantic BFS traversal. Scans Marketing_Claim nodes for proprietary/novel claim keywords (`proprietary`, `military-grade`, `in-house`, `patent-pending`, etc.) and cross-references against the codebase nodes to find contradicting evidence. Calls `confidence_engine.py` to score each contradiction.

**Output:** `data/processed/contradiction_evidence.json`  
**Current output:** 5 contradictions detected — all of the form "Claimed proprietary 'crypto', but used 'hashlib'."  
**Note:** This is Ujwal's separate "attack vector" running independently of Vaibhav's semantic BFS — both feed into Stage 9 question generation.

---

### `src/scoring/confidence_engine.py`
**Owner:** Ujwal  
**What it does:** Scores the confidence of detected contradictions on a 0.0–1.0 scale. Takes into account the specificity of the claim, the directness of the contradiction evidence, and the number of corroborating signals. Called by `contradiction_detector.py`.

---

### `src/generation/mhqg_engine.py`
**Owner:** Samhitha  
**What it does:** Template-based fallback question generator. When the LLM backend (Ollama) is unavailable or produces low-quality output, generates questions from graph templates based on chain structure. Questions are reproducible and deterministic (same chain always produces same question). Used as fallback in Stage 9.

---

### `src/generation/question_gen.py`
**Owner:** Vaibhav  
**What it does:** Primary question generator. For each hop chain from `hop_chains.json`, builds a structured evidence summary prompt and calls the LLM to generate one adversarial due diligence question. Then calls `self_evaluate_question()` to score the output 1–5.

**Key components:**
- `build_chain_summary(chain)` — formats the hop chain into a human-readable evidence description with node types, labels, edge weights, and patent metadata
- `build_prompt(chain)` — combines chain summary with category-specific focus instruction
- `categorize_question(chain)` — classifies chain as `ip_conflict`, `licence_risk`, `claim_contradiction`, `dependency`, or `feasibility`
- `call_ollama(prompt, model)` — sends prompt to local Ollama REST API at `localhost:11434`
- `self_evaluate_question(question, chain_summary, model)` — asks the same LLM to rate the question 1–5
- `build_audit_trail(chain)` — constructs step-by-step provenance list from chain nodes and edges

**LLM configuration:** Ollama phi3 model, `MAX_TOKENS=150`, temperature 0.7, 3 retry attempts

**Bug fixed during development:** `quality_score` was computed correctly by `self_evaluate_question()` but never passed to the `GeneratedQuestion` dataclass constructor — the dataclass always defaulted to `quality_score=3`. Fixed by adding `quality_score=quality_score` to the constructor call.

**Output:** `data/processed/questions.json`

---

### `src/audit/explainability_engine.py`
**Owner:** Ujwal  
**What it does:** Generates the final audited report. Reads `questions.json`, adds SHA-256 cryptographic trace IDs to each question, and writes a complete audit trail. The trace ID is computed as `SHA-256(json(evidence_chain) + question_text)[:12]` — making every output cryptographically tied to its exact evidence.

**Output:** `data/processed/audited_vc_report.json`  
**Trace ID format:** `TRC-{12-char-SHA256-hex}-{unix_timestamp}`  
**Audit status:** All items marked `MACHINE_ASSISTED_VERIFICATION`

---

### `src/retrievers/faiss_indexer.py`
**Owner:** Samhitha  
**What it does:** Wraps FAISS `IndexFlatIP` (inner product = cosine similarity on normalized vectors) for cross-domain semantic search. Used by `knowledge_fusion.py` and `entity_resolver.py`. Implements `Recall@K` tracking for evaluation purposes.

---

### `src/retrievers/retriever.py`
**Owner:** Samhitha  
**What it does:** Higher-level retrieval interface over the FAISS index. Given a query string, returns the top-K most semantically similar nodes from the knowledge graph. Used in question generation to fetch supporting evidence for a given claim.

---

### `src/extractors/legal_analyzer.py`
**Owner:** Samhitha  
**What it does:** Analyzes license metadata of dependencies. Maps library names to their known license types (MIT, Apache-2.0, GPL-3.0, etc.) and flags commercial use restrictions. Feeds into Track 4 of knowledge_fusion.py and the `has_licence_conflict` flag on hop chains.

---

### `src/extractors/license_parser.py`
**Owner:** Ujwal  
**What it does:** Parses license files and SPDX identifiers from the codebase. Writes `license_knowledge.json` for Track 4 of knowledge fusion. Currently optional — pipeline continues gracefully if this file is missing.

---

### `src/graph/entity_resolver.py` (Vaibhav's version)
**Owner:** Vaibhav  
**What it does:** Same cross-domain entity matching function as `src/resolvers/entity_resolver.py` but implemented as Vaibhav's standalone module. Uses `SCORE_THRESH = 0.45` for all matches.

---

### `src/reasoning/question_gen.py` (Vaibhav's version)
**Owner:** Vaibhav  
**What it does:** Vaibhav's standalone question generation module, used in his pipeline.py. Integrated into the merged pipeline as the primary question generator.

---

## 7. The 10-Stage Pipeline In Detail

| Stage | File | Input | Output | Time |
|-------|------|-------|--------|------|
| 1 | `whitepaper_parser.py` | `vaultchain_pitch.pdf` | `vaultchain_pitch_parsed.json` | ~0.7s |
| 2 | `github_parser.py` | `cryptosecure_startup/` | `codebase_knowledge.json`, `dependency_map.json` | ~0.8s |
| 3 | `patent_parser.py` | `data/raw/patents/` | `knowledge_base.json`, per-patent triple files | ~1.4s |
| 4 | `knowledge_fusion.py` | outputs of 1–3 | `fused_knowledge_graph.json`, `.graphml` | ~16s |
| 5 | `entity_resolver.py` | outputs of 1–3 | `entity_matches.json` | ~7s |
| 6 | `kg_builder.py` | `fused_knowledge_graph.json` | typed KG in memory | ~0.02s |
| 7 | `contradiction_detector.py` | `fused_knowledge_graph.json` | `contradiction_evidence.json` | ~0.01s |
| 8 | `hop_reasoner.py` | typed KG | `hop_chains.json` | ~0.03s |
| 9 | `question_gen.py` | `hop_chains.json` | `questions.json` | ~145–210s |
| 10 | `explainability_engine.py` | `questions.json` | `audited_vc_report.json` | ~0.03s |

**Total runtime:** ~170–240 seconds on standard laptop CPU  
**Bottleneck:** Stage 9 (question_gen) at ~88–90% of total runtime — due to local Ollama LLM inference running on CPU with phi3 model, ~35–45 seconds per question

---

## 8. What the Output Looks Like

### Sample 3-hop IP_CONFLICT question (the system's primary deliverable):

```
[q_0001] IP_CONFLICT  [!] PATENT
Score: 0.5038  |  Hops: 2  |  Chain: chain_0003  |  Backend: ollama  |  Quality: 4/5

Q: Given your startup's proprietary ECDSA Signature Verification Engine claims 
a completely in-house build without third-party libraries (as per Claim 2), 
but code referencing 'ecdsa' is found, which overlaps with active Patent 
CN110138567B held by Guangzhou Anyan Information Technology — can you provide 
a detailed freedom-to-operate analysis and evidence that your implementation 
does not infringe upon the described claims within this active patent?

Audit trail:
   1. [Claim] "Our custom ECDSA signature verification engine is built entirely 
              in-house and does not depend on any third-party cryptographic 
              libraries." --[IMPLEMENTED_BY]-->
   2. [Library] ecdsa --[REQUIRES_IP_REVIEW]-->
   3. [Patent] ECDSA-based collaborative signing method...
              (patent_id=patent_CN110138567B, assignee=Guangzhou Anyan)
```

### Pipeline Eval Results (current best run):
```
Total questions generated  : 5
With audit trail           : 5       ← Phase 1 check PASS
With licence flag          : 0
With patent flag           : 3

Category breakdown:
   ip_conflict               3
   claim_contradiction       2

Phase 1 check (all questions have audit trail): [PASS]
```

### Contradiction Detector Output (Stage 7):
```
🚨 CONTRADICTION CAUGHT: Claimed proprietary 'crypto', but used 'hashlib'.
🚨 CONTRADICTION CAUGHT: Claimed proprietary 'crypto', but used 'hashlib'.
🚨 CONTRADICTION CAUGHT: Claimed proprietary 'crypto', but used 'hashlib'.
🚨 CONTRADICTION CAUGHT: Claimed proprietary 'crypto', but used 'hashlib'.
🚨 CONTRADICTION CAUGHT: Claimed proprietary 'crypto', but used 'hashlib'.
Exported 5 Proprietary Contradictions
```

### Knowledge Fusion Summary (Stage 4):
```
Total nodes : 113
Total edges : 248

Edge breakdown:
  IMPORTS                          230
  IMPLEMENTED_BY                    12
  utilizes                           2
  stores                             2
  generates                          1
  secures                            1
```

---

## 9. Key Technical Decisions

### Why sentence-transformers (all-MiniLM-L6-v2)?
Fast, lightweight, runs on CPU, already cached from first run. Produces 384-dimensional embeddings. Used for all semantic similarity computation across the system — claim-to-dep matching, dep-to-patent matching, entity resolution.

### Why FAISS IndexFlatIP?
Exact nearest-neighbour search (no approximation error) on normalized vectors gives cosine similarity. Fast enough for graphs of 100–600 nodes. The `_BRIDGE_TOP_K` parameter limits how many connections each node makes.

### Why Ollama phi3 locally?
Zero API cost, no rate limits, no data leaves the machine (important for confidential VC deal data). Tradeoff: slow on CPU (~40s per question) and lower quality than GPT-4 or Claude.

### Why dual-label nodes?
Three teammates built separate systems with different node type naming conventions. Rather than rewrite everyone's downstream code, every node carries both label systems simultaneously. `label` serves Samhitha's mhqg_engine. `node_type` serves Vaibhav's hop_reasoner. Both are set by `_make_node_attrs()` using the `_LABEL_TO_NODE_TYPE` mapping dict.

### Why SHA-256 audit trails?
IP risk assessments can end up in legal proceedings. A cryptographic trace ID ties every generated question to the exact evidence that produced it — making the output legally defensible. No other automated due diligence tool provides this.

### Why `_DEP_ENRICHMENT`?
Library names like `hashlib` score near-zero against claim text like "military-grade cryptographic hashing module" using raw cosine similarity. The `_DEP_ENRICHMENT` dict maps each library name to a semantic expansion string (e.g. `hashlib` → `"cryptographic hashing security hash digest"`), raising the cosine score from ~0.01 to ~0.61 for correct matches.

---

## 10. Known Limitations

**Patent data quality:** The synthetic benchmark marks all patents with `legal_risk_flag: false` regardless of actual status. This was causing Bridge Layer 2 to filter all patent nodes out. Fixed by removing the filter, but the correct fix for production is to use real USPTO API metadata.

**Single-hop dominance:** Most questions are currently 1–2 hops. True 3-hop chains (Claim→Library→Patent) require all three of: a named dep node (from requirements.txt), a patent node, and a SIMILAR_TO edge connecting them. This is sensitive to dep vocabulary vs patent vocabulary overlap.

**Quality score mismatch:** `self_evaluate_question()` in Stage 9 was computing a score but it was never passed to the `GeneratedQuestion` dataclass — always defaulting to 3. Fixed by adding `quality_score=quality_score` to the constructor.

**Stage 9 is the bottleneck:** 88–90% of total runtime is LLM inference. 5 questions take ~3 minutes on CPU. For production, switching to a GPU or using the Anthropic API backend would reduce this to under 30 seconds total.

**`load_dependencies` indentation bug:** The `load_dependencies` method was accidentally defined at module level (not inside the class) during the merger, causing `AttributeError: 'KnowledgeFusionPipeline' object has no attribute 'load_dependencies'`. Fixed by re-indenting lines 219–296.

**Contradiction detector over-fires:** All 5 contradictions are the same (`Claimed proprietary 'crypto', but used 'hashlib'`). This is because the keyword match triggers on every claim that contains "proprietary" or "crypto" — not just once per distinct claim-library pair. Needs deduplication logic.

---

## 11. How To Run

### Prerequisites
```powershell
# Install Ollama from https://ollama.com
ollama pull phi3

# Install Python dependencies
pip install -r requirements.txt

# Activate venv
.\venv\Scripts\Activate
```

### Basic run
```powershell
python src\pipeline.py \
  --whitepaper data\raw\pitch_decks\vaultchain_pitch.pdf \
  --repo       data\raw\repositories\cryptosecure_startup \
  --patents    data\raw\patents \
  --output     data\processed\ \
  --max-questions 5 \
  --backend ollama \
  --model phi3
```

### Clean run (clear previous outputs first)
```powershell
Remove-Item data\processed\* -Recurse -Force
python src\pipeline.py --whitepaper data\raw\pitch_decks\vaultchain_pitch.pdf --repo data\raw\repositories\cryptosecure_startup --patents data\raw\patents --output data\processed\ --max-questions 5 --backend ollama --model phi3
```

### Key CLI parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `--fusion-threshold` | 0.40 | Minimum cosine similarity for Bridge Layer 1 |
| `--resolver-threshold` | 0.45 | Minimum similarity for entity matching |
| `--chain-threshold` | 0.28 | Minimum chain score to keep in BFS |
| `--max-hops` | 3 | Maximum chain length in BFS |
| `--max-questions` | None | Limit LLM calls (use 5 for fast testing) |
| `--backend` | ollama | `ollama` or `anthropic` |
| `--model` | phi3 | Ollama model name |
| `--dry-run` | False | Skip LLM, use template questions |

---


