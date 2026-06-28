"""
inspect_structures.py  — run once to expose JSON/function-name issues
    python inspect_structures.py
"""
import json, ast, sys
from pathlib import Path

ROOT      = Path(__file__).parent
PROCESSED = ROOT / "data" / "processed"
SRC       = ROOT / "src"

SEP = "─" * 70

# ── 1. Dump expense_ninja_pitch_parsed.json ──────────────────────────────────
parsed_path = PROCESSED / "expense_ninja_pitch_parsed.json"
print(SEP)
print("1. expense_ninja_pitch_parsed.json — FULL STRUCTURE")
print(SEP)
if parsed_path.exists():
    data = json.loads(parsed_path.read_text())
    print(json.dumps(data, indent=2))
else:
    print("  FILE NOT FOUND")

# ── 2. patent_parser.py — top-level function names ──────────────────────────
pp_path = SRC / "extractors" / "patent_parser.py"
print(f"\n{SEP}")
print("2. patent_parser.py — exported function names")
print(SEP)
if pp_path.exists():
    tree = ast.parse(pp_path.read_text())
    fns = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    print("  Functions defined:", fns)
    # Also print the first 60 lines so we can see expected input format
    lines = pp_path.read_text().splitlines()
    print("\n  First 60 lines:")
    for i, l in enumerate(lines[:60], 1):
        print(f"  {i:>3}  {l}")
else:
    print("  FILE NOT FOUND")

# ── 3. pipeline.py — github_parser stage snippet ────────────────────────────
pl_path = SRC / "pipeline.py"
print(f"\n{SEP}")
print("3. pipeline.py — lines mentioning github_parser")
print(SEP)
if pl_path.exists():
    lines = pl_path.read_text().splitlines()
    for i, l in enumerate(lines, 1):
        if "github" in l.lower() or "dep_map" in l.lower() or "dependency_map" in l.lower():
            print(f"  {i:>4}  {l}")
else:
    print("  FILE NOT FOUND")

# ── 4. fused_knowledge_graph.json — first 2 dep nodes ───────────────────────
graph_path = PROCESSED / "fused_knowledge_graph.json"
print(f"\n{SEP}")
print("4. fused_knowledge_graph.json — sample Dependency/Code_Module nodes")
print(SEP)
if graph_path.exists():
    g = json.loads(graph_path.read_text())
    nodes = g.get("nodes", [])
    sample = [
        n for n in nodes
        if n.get("node_type") in ("Dependency","Code_Module")
        or n.get("label")    in ("Dependency","Code_Module")
        or n.get("type")     in ("Dependency","Code_Module")
    ][:5]
    if sample:
        print(json.dumps(sample, indent=2))
    else:
        print("  No Dep/Module nodes found. First 3 nodes of any type:")
        print(json.dumps(nodes[:3], indent=2))
else:
    print("  FILE NOT FOUND")