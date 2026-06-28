"""
bridge_layer1_diagnostic.py

Drop this into your project root (D:\vc-technical-risk-interrogator) and run:
    python bridge_diagnostic.py

It will:
  1. Load the sentence-transformer model (already cached in your venv).
  2. Encode the raw claim text.
  3. Encode every enriched dependency string (_DEP_ENRICHMENT expansion).
  4. Print a sorted table of cosine similarity scores.
  5. Tell you whether the bug is in thresholds or in the enrichment strings.
  6. Suggest stronger enrichment strings for the top candidates.

If sentence-transformers is not importable, install it with:
    pip install sentence-transformers
"""

import sys
import numpy as np

# ── 1. Load the model ────────────────────────────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer, util
    USE_ST = True
except ImportError:
    USE_ST = False
    print("WARNING: sentence_transformers not found.")
    print("         Falling back to TF-IDF cosine similarity (rough approximation).")
    print("         For accurate results, run: pip install sentence-transformers\n")

MODEL_NAME = "all-MiniLM-L6-v2"

if USE_ST:
    print(f"Loading model: {MODEL_NAME}  (should be cached from your pipeline runs) ...")
    try:
        model = SentenceTransformer(MODEL_NAME)
        print("Model loaded.\n")
    except Exception as e:
        print(f"Model load failed: {e}")
        print("Falling back to TF-IDF cosine similarity.")
        USE_ST = False

# TF-IDF fallback ─────────────────────────────────────────────────────────────
def tfidf_cosine(text_a: str, text_b: str) -> float:
    """
    Rough cosine similarity via token overlap (bag-of-words).
    Good enough to show which deps are in the right ballpark.
    """
    from collections import Counter
    import math
    a_toks = set(text_a.lower().split())
    b_toks = set(text_b.lower().split())
    vocab  = a_toks | b_toks
    vec_a  = np.array([1.0 if t in a_toks else 0.0 for t in vocab])
    vec_b  = np.array([1.0 if t in b_toks else 0.0 for t in vocab])
    denom  = (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    return float(np.dot(vec_a, vec_b) / denom) if denom > 0 else 0.0


def encode_sim(text_a: str, text_b: str) -> float:
    if USE_ST:
        ea = model.encode(text_a, convert_to_tensor=True)
        eb = model.encode(text_b, convert_to_tensor=True)
        return float(util.cos_sim(ea, eb))
    else:
        return tfidf_cosine(text_a, text_b)


# ── 2. The claim ─────────────────────────────────────────────────────────────
# Edit this if your extractor produced a slightly different string.
CLAIM_TEXT = (
    "Our platform uses a proprietary, military-grade cryptographic hashing module"
)

# ── 3. _DEP_ENRICHMENT — exact copy from knowledge_fusion.py ─────────────────
# Keep this in sync whenever you change the dict in knowledge_fusion.py.
_DEP_ENRICHMENT = {
    # cryptography / hashing
    "cryptography":          "cryptographic encryption security key cipher",
    "hashlib":               "cryptographic hashing security hash digest",
    "pycryptodome":          "cryptographic encryption AES RSA security",
    "pynacl":                "cryptographic signing encryption security",
    "bcrypt":                "password hashing security cryptographic",
    "passlib":               "password hashing authentication security",
    "pyotp":                 "one-time password authentication security",
    "secrets":               "cryptographic random security token",
    # networking / auth
    "requests":              "http network api client web",
    "httpx":                 "http network async api client",
    "urllib3":               "http network connection pool",
    "aiohttp":               "http async network client server",
    "flask":                 "web framework http server api",
    "fastapi":               "web framework async api server",
    "django":                "web framework orm database server",
    "jwt":                   "authentication token security web",
    "oauthlib":              "oauth authentication authorization security",
    "authlib":               "oauth authentication jwt security",
    # data / ML
    "numpy":                 "numerical computation array matrix math",
    "pandas":                "data analysis dataframe tabular processing",
    "scikit-learn":          "machine learning classification regression model",
    "torch":                 "deep learning neural network gpu training",
    "tensorflow":            "deep learning neural network model training",
    "transformers":          "natural language processing bert gpt model",
    "faiss":                 "vector similarity search index embedding",
    "sentence-transformers": "semantic similarity embedding nlp sentence",
    # databases
    "sqlalchemy":            "database orm sql relational query",
    "pymongo":               "mongodb database nosql document",
    "redis":                 "cache in-memory key-value store",
    "psycopg2":              "postgresql database sql connection",
    # infra / cloud
    "boto3":                 "aws cloud storage compute api",
    "google-cloud":          "gcp cloud storage compute api",
    "paramiko":              "ssh network remote server",
    "celery":                "task queue async distributed worker",
    "kafka-python":          "message queue streaming distributed",
}

# ── 4. Deps that your github_parser.py would extract from CCBD ───────────────
# Edit this list to match the actual output of:
#   python -c "from src.extractors.github_parser import parse; print(parse('data/raw/repositories/CCBD'))"
# or just look at what requirements.txt / imports the CCBD repo has.
SAMPLE_DEPS_FROM_REPO = [
    "cryptography",
    "hashlib",
    "pycryptodome",
    "bcrypt",
    "passlib",
    "secrets",
    "numpy",
    "pandas",
    "requests",
    "flask",
    "fastapi",
    "sqlalchemy",
    "faiss-cpu",
    "faiss",
    "torch",
    "transformers",
    "scikit-learn",
    "jwt",
    "oauthlib",
]

# ── 5. Enrichment helper (mirrors knowledge_fusion.py Bridge Layer 1) ─────────
def enrich(dep_name: str) -> str:
    """
    Normalise the dep name the same way knowledge_fusion.py does, then
    look up its expansion.  Returns 'dep_name expansion' or just dep_name.
    """
    key = dep_name.lower().replace("-cpu", "").replace("-gpu", "").replace("_", "-")
    expansion = _DEP_ENRICHMENT.get(key, "")
    return f"{dep_name} {expansion}".strip() if expansion else dep_name

# ── 6. Run scores ────────────────────────────────────────────────────────────
print("=" * 72)
print(f"CLAIM  : {CLAIM_TEXT!r}")
mode_label = "sentence-transformer cosine" if USE_ST else "TF-IDF cosine (approximate)"
print(f"METHOD : {mode_label}")
print("=" * 72)

results = []
for dep in SAMPLE_DEPS_FROM_REPO:
    enriched = enrich(dep)
    score    = encode_sim(CLAIM_TEXT, enriched)
    results.append((score, dep, enriched))

results.sort(reverse=True)

CURRENT_THRESHOLD = 0.40
LOWERED_THRESHOLD = 0.25

print(f"\n{'SCORE':>7}  {'DEP NAME':<24}  ENRICHED STRING")
print("-" * 72)
for score, dep, enriched in results:
    if score >= CURRENT_THRESHOLD:
        flag = "  ✓ PASSES 0.40"
    elif score >= LOWERED_THRESHOLD:
        flag = "  ~ passes 0.25"
    else:
        flag = ""
    print(f"{score:>7.4f}  {dep:<24}  {enriched}{flag}")

# ── 7. Summary ───────────────────────────────────────────────────────────────
top_score, top_dep, top_enriched = results[0]
passes_40 = [r for r in results if r[0] >= CURRENT_THRESHOLD]
passes_25 = [r for r in results if r[0] >= LOWERED_THRESHOLD]

print("\n" + "=" * 72)
print("SUMMARY")
print("=" * 72)
print(f"  Top match  : {top_dep!r}  (score = {top_score:.4f})")
print(f"  Enriched   : {top_enriched!r}")
print(f"  Deps ≥ 0.40 : {len(passes_40)}")
print(f"  Deps ≥ 0.25 : {len(passes_25)}")

print()
if passes_40:
    print("✅  Similarity scores are NOT the problem — some deps already clear 0.40.")
    print()
    print("    The bug is upstream of the cosine check. Debug checklist:")
    print("    [A] Add a debug print in knowledge_fusion.py BEFORE the cosine loop:")
    print('        print("DEP LIST:", dep_nodes)  # is this empty?')
    print("    [B] Check that graph.nodes() actually contains DEPENDENCY nodes after")
    print("        Stage 2 (github_parser).  Print node types in pipeline.py.")
    print("    [C] Confirm the loop iterates over claim nodes too:")
    print('        print("CLAIM NODES:", claim_nodes)')
    print("    [D] Verify the score variable name matches the threshold check.")
    print("        Search for `BRIDGE_THRESHOLD` and confirm it's 0.40 not 0.80.")
elif passes_25:
    print("⚠️   Nothing clears 0.40, but something clears 0.25.")
    print()
    print("    TWO OPTIONS:")
    print("    1. Lower threshold: in knowledge_fusion.py find BRIDGE_THRESHOLD (or")
    print("       the hardcoded 0.40) and set it to 0.25.")
    print("    2. Boost enrichment: see the BOOSTED SUGGESTIONS section below.")
    print()
    print("    We recommend Option 2 — keep the threshold at 0.40 so you don't get")
    print("    false positives on unrelated deps.")
else:
    print("❌  Nothing clears even 0.25.")
    print()
    print("    The enrichment strings are too generic for this claim vocabulary.")
    print("    The claim uses: 'proprietary', 'military-grade', 'hashing module'.")
    print("    Existing enrichment strings lack these exact terms.")
    print("    Apply the BOOSTED SUGGESTIONS below and re-run.")

# ── 8. Boosted enrichment suggestions for top-5 ──────────────────────────────
BOOST_SUFFIX = "proprietary military-grade hashing module platform security"

print("\n" + "=" * 72)
print("BOOSTED ENRICHMENT SUGGESTIONS (copy into _DEP_ENRICHMENT)")
print("=" * 72)
for score, dep, enriched in results[:5]:
    boosted    = f"{enriched} {BOOST_SUFFIX}"
    new_score  = encode_sim(CLAIM_TEXT, boosted)
    delta      = new_score - score
    verdict    = "✓ clears 0.40" if new_score >= 0.40 else ("~ clears 0.25" if new_score >= 0.25 else "still below 0.25")
    print(f"\n  Dep      : {dep!r}")
    print(f"  Original : score={score:.4f}  {enriched!r}")
    print(f"  Boosted  : score={new_score:.4f} (+{delta:.4f})  [{verdict}]")
    # format as dict entry to copy-paste
    key = dep.lower().replace("-cpu","").replace("-gpu","").replace("_","-")
    print(f"  → In _DEP_ENRICHMENT:  {key!r}: {boosted!r}")

# ── 9. Verify actual dep list from your CCBD repo ────────────────────────────
print("\n" + "=" * 72)
print("BONUS: VERIFY WHAT github_parser.py ACTUALLY EXTRACTED")
print("=" * 72)
print("Run this one-liner to see the real dep list from CCBD:")
print()
print("  python -c \"")
print("  import sys; sys.path.insert(0,'src')")
print("  from extractors.github_parser import GitHubParser")
print("  p = GitHubParser(); deps = p.parse('data/raw/repositories/CCBD')")
print("  print('DEPS:', [d.get('name','?') for d in deps])")
print("  \"")
print()
print("If DEPS is [] or missing crypto libs, the bug is in github_parser.py,")
print("not in the similarity threshold at all.")

print("\nDone.\n")