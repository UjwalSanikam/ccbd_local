"""
diagnose.py  —  Drop in D:\\vc-technical-risk-interrogator\\ and run:
    python diagnose.py

Checks three failure points:
  [A] dependency_map.json missing
  [B] patent_mock.txt producing 0 triples
  [C] cosine similarity scores between claim and enriched dep strings
"""

import json
import sys
import numpy as np
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
PROCESSED = ROOT / "data" / "processed"
RAW       = ROOT / "data" / "raw"

# Adjust if your repo folder name differs
REPO_CANDIDATES = [
    RAW / "repositories" / "MULTI_HOP_VC",
    RAW / "repositories" / "CCBD",
]
PATENT_FILE = RAW / "patents" / "patent_mock.txt"

SEP = "=" * 70


# ── [A] dependency_map.json ──────────────────────────────────────────────────
def check_dependency_map():
    print(f"\n{SEP}")
    print("[A] dependency_map.json diagnosis")
    print(SEP)

    dep_map_path = PROCESSED / "dependency_map.json"
    if dep_map_path.exists():
        with open(dep_map_path) as f:
            dm = json.load(f)
        deps = dm.get("dependencies", dm.get("packages", []))
        print(f"  ✓ Found — {len(deps)} entries")
        for d in deps[:5]:
            print(f"      {d}")
        return

    print("  ✗ NOT FOUND in data/processed/")
    print("  → This means knowledge_fusion.py Bridge Layer1 has no flat dep list.")
    print()

    # Find the repo root
    repo_root = None
    for c in REPO_CANDIDATES:
        if c.exists():
            repo_root = c
            break

    if repo_root is None:
        print("  ✗ Could not locate repo folder under data/raw/repositories/")
        print("    Check that your --repo path exists.")
        return

    print(f"  Repo found at: {repo_root}")

    # Check if requirements.txt / package.json / setup.py exist
    for fname in ("requirements.txt", "package.json", "setup.py", "pyproject.toml"):
        p = repo_root / fname
        status = "✓" if p.exists() else "✗"
        print(f"    {status}  {fname}")

    print()
    print("  ROOT CAUSE: pipeline.py runs github_parser but the stage function")
    print("  likely calls parse_repo() without also calling write_outputs().")
    print("  FIX → see Section [A-FIX] at bottom of this report.")


# ── [B] patent_mock.txt ──────────────────────────────────────────────────────
def check_patent_file():
    print(f"\n{SEP}")
    print("[B] patent_mock.txt / patent parser diagnosis")
    print(SEP)

    if not PATENT_FILE.exists():
        print(f"  ✗ File not found: {PATENT_FILE}")
        return

    raw = PATENT_FILE.read_text(encoding="utf-8", errors="replace")
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    print(f"  File exists — {len(lines)} non-empty lines")
    print()
    print("  First 20 lines:")
    for i, line in enumerate(lines[:20], 1):
        print(f"    {i:>3}  {line[:100]}")

    print()
    # Heuristic: look for what the parser expects
    tab_lines   = [l for l in lines if "\t" in l]
    pipe_lines  = [l for l in lines if "|" in l]
    json_lines  = [l for l in lines if l.startswith("{")]
    colon_triples = [l for l in lines if l.count(":") >= 2]

    print("  Format detection:")
    print(f"    Tab-separated lines  : {len(tab_lines)}")
    print(f"    Pipe-separated lines : {len(pipe_lines)}")
    print(f"    JSON object lines    : {len(json_lines)}")
    print(f"    Lines with 2+ colons : {len(colon_triples)}")

    # Try to load patent_parser and call it directly
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from extractors.patent_parser import parse_patents
        triples = parse_patents(PATENT_FILE)
        print(f"\n  parse_patents() returned: {len(triples)} triple(s)")
        for t in triples[:5]:
            print(f"    {t}")
        if len(triples) == 0:
            print("\n  ROOT CAUSE: parser returned 0 triples.")
            print("  FIX → see Section [B-FIX] at bottom of this report.")
    except Exception as e:
        print(f"\n  Could not import patent_parser: {e}")
        print("  Check src/extractors/patent_parser.py exists and is importable.")


# ── [C] Cosine similarity scores ─────────────────────────────────────────────
def check_similarity_scores():
    print(f"\n{SEP}")
    print("[C] Cosine similarity: claim vs enriched dependency strings")
    print(SEP)

    # 1. Load claim text
    parsed_path = PROCESSED / "expense_ninja_pitch_parsed.json"
    if not parsed_path.exists():
        print("  ✗ expense_ninja_pitch_parsed.json not found — run stage 1 first.")
        return

    with open(parsed_path) as f:
        parsed = json.load(f)

    raw_claims = parsed.get("claims", [])
    claim_texts = []
    for c in raw_claims:
        if isinstance(c, dict):
            claim_texts.append(c.get("text", c.get("claim", str(c))))
        else:
            claim_texts.append(str(c))

    if not claim_texts:
        print("  ✗ No claims found in parsed JSON.")
        return

    print(f"  Claims loaded: {len(claim_texts)}")
    for i, t in enumerate(claim_texts, 1):
        print(f"    {i}. {t[:120]}")

    # 2. Load codebase nodes from fused graph
    graph_path = PROCESSED / "fused_knowledge_graph.json"
    if not graph_path.exists():
        print("\n  ✗ fused_knowledge_graph.json not found — run stage 4 first.")
        return

    with open(graph_path) as f:
        graph = json.load(f)

    nodes = graph.get("nodes", [])
    # Accept nodes whose label OR node_type marks them as Dep or Module
    dep_nodes = [
        n for n in nodes
        if n.get("node_type") in ("Dependency", "Code_Module")
        or n.get("label") in ("Dependency", "Code_Module")
        or n.get("type") in ("Dependency", "Code_Module")
    ]
    print(f"\n  Graph: {len(nodes)} nodes total, {len(dep_nodes)} Dependency/Code_Module nodes")

    if not dep_nodes:
        print("  ✗ No Dependency or Code_Module nodes — check github_parser output.")
        # Show what node types actually exist
        types = {}
        for n in nodes:
            t = n.get("node_type") or n.get("label") or n.get("type") or "unknown"
            types[t] = types.get(t, 0) + 1
        print("  Actual node types in graph:")
        for t, cnt in sorted(types.items(), key=lambda x: -x[1]):
            print(f"    {t:30s} {cnt}")
        return

    # 3. Replicate the _DEP_ENRICHMENT dict from knowledge_fusion.py
    #    (extend this to match whatever is in your actual file)
    _DEP_ENRICHMENT = {
        # Security / crypto
        "hashlib":       "cryptographic hashing security sha256 md5",
        "cryptography":  "cryptographic encryption decryption security ssl tls",
        "pycryptodome":  "cryptographic cipher encryption AES RSA",
        "pycryptodomex": "cryptographic cipher encryption AES RSA",
        "bcrypt":        "password hashing security cryptographic",
        "passlib":       "password hashing cryptographic security",
        "nacl":          "cryptographic public key encryption signing",
        "pyotp":         "one-time password authentication security",
        "secrets":       "cryptographically secure random token generation",
        "ssl":           "secure socket layer tls cryptographic certificate",
        "hmac":          "hash-based message authentication cryptographic",
        # Auth / identity
        "jwt":           "JSON web token authentication authorization",
        "pyjwt":         "JSON web token authentication authorization",
        "oauthlib":      "OAuth authentication authorization protocol",
        "authlib":       "OAuth OpenID authentication security",
        "flask-login":   "user authentication session management",
        "django-auth":   "user authentication permission security",
        # Data / ML
        "numpy":         "numerical array computation matrix",
        "pandas":        "data analysis tabular dataframe",
        "scikit-learn":  "machine learning classification regression",
        "torch":         "deep learning neural network pytorch",
        "tensorflow":    "deep learning neural network model",
        "faiss":         "vector similarity search index embedding",
        "sentence-transformers": "sentence embedding semantic similarity NLP",
        # Web / API
        "flask":         "web framework HTTP REST API",
        "django":        "web framework HTTP REST database ORM",
        "fastapi":       "web framework async REST API",
        "requests":      "HTTP client web API network",
        "aiohttp":       "async HTTP client server web",
        # Storage / DB
        "sqlalchemy":    "database ORM SQL relational",
        "pymongo":       "MongoDB NoSQL database",
        "redis":         "in-memory cache key-value store",
        "elasticsearch": "search index full-text query",
        # Graph
        "networkx":      "graph network node edge algorithm",
        "neo4j":         "graph database cypher query knowledge",
        "rdflib":        "RDF knowledge graph semantic triple",
    }

    # 4. Embed everything and score
    print("\n  Loading sentence-transformer model (all-MiniLM-L6-v2)...")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("  ✗ sentence-transformers not installed in this venv.")
        return

    model = SentenceTransformer("all-MiniLM-L6-v2")

    for claim_text in claim_texts:
        print(f"\n  ── Claim: \"{claim_text[:90]}{'...' if len(claim_text)>90 else ''}\"")

        claim_emb = model.encode(claim_text, normalize_embeddings=True)

        rows = []
        for node in dep_nodes:
            raw_id = node.get("id", node.get("name", ""))
            # Strip path prefix to get bare package name
            pkg = raw_id.split(":")[-1].split("/")[-1].split(".")[-1].lower()

            enrichment = _DEP_ENRICHMENT.get(pkg, "")
            enriched_str = f"{pkg} {enrichment}".strip() if enrichment else pkg

            dep_emb = model.encode(enriched_str, normalize_embeddings=True)
            score = float(np.dot(claim_emb, dep_emb))
            rows.append((score, pkg, enriched_str, raw_id))

        rows.sort(reverse=True)

        print(f"\n  {'SCORE':>7}  {'PACKAGE':<22}  ENRICHED STRING")
        print(f"  {'-'*7}  {'-'*22}  {'-'*40}")
        for score, pkg, enriched, raw_id in rows[:20]:
            flag = ""
            if score >= 0.40:
                flag = "  ◄ ABOVE 0.40"
            elif score >= 0.30:
                flag = "  ◄ above 0.30"
            elif score >= 0.20:
                flag = "  · above 0.20"
            print(f"  {score:>7.4f}  {pkg:<22}  {enriched[:50]:<50}{flag}")

        if rows:
            best_score, best_pkg, best_str, _ = rows[0]
            print()
            print(f"  ► Highest score : {best_score:.4f}  ({best_pkg})")
            print(f"  ► Current threshold (fusion) : 0.40")
            print(f"  ► Minimum threshold to get ≥1 edge : {best_score - 0.001:.4f}")

            if best_score < 0.20:
                print()
                print("  ⚠  VERY LOW SCORES (<0.20). Most likely causes:")
                print("     1. dep nodes have no useful text — only bare Python import names")
                print("     2. The node 'id' field isn't a recognisable package name")
                print("     3. _DEP_ENRICHMENT keys don't match what's in your graph")
                print("     → Show a sample node below:")
                for n in dep_nodes[:3]:
                    print(f"        {json.dumps(n, indent=6)[:300]}")
            elif best_score < 0.35:
                print()
                print("  ⚠  SCORES IN 0.20–0.35 RANGE.")
                print("     Lowering threshold to 0.20 will create edges,")
                print("     but enrichment strings need improvement for precision.")
                print("     Best fix: improve _DEP_ENRICHMENT for the top packages above.")


# ── Fixes summary ─────────────────────────────────────────────────────────────
def print_fixes():
    print(f"\n{SEP}")
    print("FIXES")
    print(SEP)

    print("""
[A-FIX]  dependency_map.json missing
─────────────────────────────────────
In pipeline.py, find the github_parser stage function.
It likely calls something like:
    result = github_parser.parse_repo(repo_path)
But never writes dependency_map.json.  Add after that call:

    from pathlib import Path
    import json
    dep_map_path = Path("data/processed/dependency_map.json")
    dep_map_path.parent.mkdir(parents=True, exist_ok=True)
    dep_map = result.get("dependency_map", result.get("dep_map", {}))
    dep_map_path.write_text(json.dumps(dep_map, indent=2))

Or if github_parser.py already has a write_outputs() / save() function,
call it explicitly and pass output_dir=Path("data/processed").

[B-FIX]  patent_mock.txt — 0 triples
─────────────────────────────────────
The parser expects a specific format (tab-separated triples, JSON, etc.).
Run this script to see what's in the file and what format it uses.
Then either:
  (a) Fix patent_mock.txt to match the parser's expected format, OR
  (b) Add a format-detection fallback in patent_parser.py.

A minimal tab-separated triple that most parsers accept:
  US1234567\\tcryptographic hashing\\tSHA-256 hash function for data integrity

[C-FIX]  Bridge Layer1 similarity threshold
────────────────────────────────────────────
Based on the scores above, pick the right fix:

  IF max score > 0.35:
    Lower _DEFAULT_THRESHOLD in knowledge_fusion.py to 0.25 (already tried),
    and pass --fusion-threshold 0.25 on the CLI.

  IF max score is 0.15–0.35:
    The enrichment strings in _DEP_ENRICHMENT aren't matching.
    Update them to include phrases that appear in the claim, e.g.:
      "hashlib": "proprietary military-grade cryptographic hashing module SHA-256"
    Then re-run.

  IF max score < 0.15:
    The dep node IDs in the graph don't look like package names.
    Print dep_nodes[:3] to see what the actual node structure is,
    then fix the key lookup in Bridge Layer1 of knowledge_fusion.py.
""")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(SEP)
    print("VC PIPELINE DIAGNOSTIC")
    print("Run from: D:\\vc-technical-risk-interrogator\\")
    print(SEP)

    check_dependency_map()
    check_patent_file()
    check_similarity_scores()
    print_fixes()

    print(f"\n{SEP}")
    print("END OF DIAGNOSTIC")
    print(SEP)
    