"""
pipeline.py — End-to-End Pipeline Orchestrator
===============================================
Multi-Hop Reasoning System for VC Technical Due Diligence

Runs the full pipeline in sequence:
    1.  whitepaper_parser      → whitepaper claims JSON
    2.  github_parser          → codebase knowledge JSON
    3.  patent_parser          → patent triples JSON
    4.  knowledge_fusion       → fused_knowledge_graph.json
    5.  entity_resolver        → cross-domain entity matches JSON
    6.  kg_builder             → typed knowledge graph JSON
    7.  contradiction_detector → contradiction_evidence.json
    8.  hop_reasoner           → scored hop chains JSON
    9.  question_gen           → due-diligence questions JSON  ← primary deliverable
    10. explainability_engine  → audited_vc_report.json       ← audit trail

Logs latency at every stage. This is your Phase 3 optimization map:
whichever stage is slowest is where to tune first.

Usage:
    python src/pipeline.py --whitepaper data/raw/startup.pdf
                           --repo       data/raw/startup_repo/
                           --patents    data/raw/patents/
                           --output     data/processed/

    python src/pipeline.py --whitepaper data/raw/startup.pdf --dry-run
    python src/pipeline.py --whitepaper data/raw/startup.pdf --max-questions 10
    python src/pipeline.py --whitepaper data/raw/startup.pdf --backend ollama --model phi3
"""

import json
import os
import time
import logging
import argparse
import sys
from pathlib import Path
from typing import Optional

import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Add src/ to path so sibling modules are importable
sys.path.insert(0, str(Path(__file__).parent))


# ── Timing helper ─────────────────────────────────────────────────────────────

class StageTimer:
    """Tracks latency per pipeline stage for the optimization map."""

    def __init__(self):
        self.times: dict[str, float] = {}
        self._start: Optional[float] = None
        self._stage: Optional[str]   = None

    def start(self, stage: str):
        self._stage = stage
        self._start = time.perf_counter()
        logger.info("━━━ STAGE: %s ━━━", stage.upper())

    def stop(self):
        if self._stage and self._start:
            elapsed = time.perf_counter() - self._start
            self.times[self._stage] = round(elapsed, 2)
            logger.info("✓ %s completed in %.2fs", self._stage, elapsed)

    def report(self) -> dict:
        total = sum(self.times.values())
        return {
            "stage_times_seconds": self.times,
            "total_seconds":       round(total, 2),
            "slowest_stage":       max(self.times, key=self.times.get) if self.times else None,
        }

    def print_report(self):
        print(f"\n{'='*60}")
        print("  PIPELINE TIMING REPORT  (your Phase 3 optimization map)")
        print(f"{'='*60}")
        total = sum(self.times.values())
        for stage, t in self.times.items():
            pct = (t / total * 100) if total > 0 else 0
            bar = "#" * int(pct / 5)
            print(f"  {stage:<25} {t:>6.2f}s  {bar} {pct:.0f}%")
        print(f"  {'-'*56}")
        print(f"  {'TOTAL':<25} {total:>6.2f}s")
        if self.times:
            slowest = max(self.times, key=self.times.get)
            print(f"\n  Bottleneck -> {slowest} ({self.times[slowest]:.2f}s)")
            print(f"  Tune this first in Phase 3.")
        print(f"{'='*60}\n")


# ── Stage runners ─────────────────────────────────────────────────────────────

# ── Stage 1: Whitepaper parser ────────────────────────────────────────────────

def run_whitepaper_parser(
    pdf_path: Path,
    output_dir: Path,
    force_ocr: bool = False,
) -> Optional[Path]:
    from extractors.whitepaper_parser import WhitepaperParser, write_output
    try:
        p      = WhitepaperParser(pdf_path, force_ocr=force_ocr)
        result = p.parse()
        out    = write_output(result, output_dir)
        logger.info(
            "Whitepaper: %d claims, %d assertions, %d entities",
            result.statistics["technical_claims_extracted"],
            result.statistics["feature_assertions_extracted"],
            result.statistics["unique_entities_found"],
        )
        return out
    except Exception as e:
        logger.error("whitepaper_parser failed: %s", e, exc_info=True)
        return None


# ── Stage 2: GitHub parser ────────────────────────────────────────────────────

def run_github_parser(
    repo_path: Path,
    output_dir: Path,
) -> Optional[Path]:
    from extractors.github_parser import (
        build_dependency_map, build_import_graph,
        build_codebase_knowledge,
    )
    try:
        dep_map                       = build_dependency_map(repo_path)
        import_graph, import_analysis = build_import_graph(repo_path)
        combined                      = build_codebase_knowledge(
            dep_map, import_analysis, import_graph
        )

        if combined.get("import_graph_analysis"):
            combined["import_graph_analysis"] = {
                k: v for k, v in combined["import_graph_analysis"].items()
                if k != "all_imports_raw"
            }

        out = output_dir / "codebase_knowledge.json"
        out.write_text(json.dumps(combined, indent=2), encoding="utf-8")
        dep_out = output_dir / "dependency_map.json"
        dep_out.write_text(json.dumps(dep_map, indent=2), encoding="utf-8")
        logger.info("Dependency map written → %s", dep_out)
        logger.info(
            "Codebase: %d deps, %d internal modules",
            dep_map["metadata"]["total_dependencies"],
            import_analysis["metadata"]["internal_modules"],
        )
        return out
    except Exception as e:
        logger.error("github_parser failed: %s", e, exc_info=True)
        return None


# ── Stage 3: Patent parser ────────────────────────────────────────────────────

def run_patent_parser(
    patents_dir: Path,
    output_dir: Path,
) -> Optional[Path]:
    from extractors.patent_parser import process_directory
    try:
        triples = process_directory(str(patents_dir), str(output_dir))
        out     = output_dir / "knowledge_base.json"
        logger.info("Patents: %d triples extracted", len(triples))
        return out
    except Exception as e:
        logger.error("patent_parser failed: %s", e, exc_info=True)
        return None


# ── Stage 4: Knowledge fusion ─────────────────────────────────────────────────

def run_knowledge_fusion(
    data_root: Path,
    threshold: float = 0.40,
) -> Optional[Path]:
    from graph.knowledge_fusion import KnowledgeFusionPipeline
    try:
        pipeline = KnowledgeFusionPipeline(data_root, similarity_threshold=threshold)
        pipeline.fuse_knowledge_domains()
        pipeline.export_fused_graph()
        fused_path = data_root / "processed" / "fused_knowledge_graph.json"
        return fused_path if fused_path.exists() else None
    except Exception as e:
        logger.error("knowledge_fusion failed: %s", e, exc_info=True)
        return None


# ── Stage 5: Entity resolver ──────────────────────────────────────────────────

def run_entity_resolver(
    whitepaper_json: Path,
    codebase_json:   Path,
    patent_json:     Path,
    output_dir:      Path,
    threshold:       float = 0.45,
) -> Optional[Path]:
    from resolvers.entity_resolver import resolve_entities
    out = output_dir / "entity_matches.json"
    try:
        matches = resolve_entities(
            whitepaper_path = whitepaper_json,
            codebase_path   = codebase_json,
            patent_path     = patent_json,
            output_path     = out,
            threshold       = threshold,
        )
        logger.info("Entity resolver: %d cross-domain matches", len(matches))
        return out
    except Exception as e:
        logger.error("entity_resolver failed: %s", e, exc_info=True)
        return None


# ── Stage 6: KG builder ───────────────────────────────────────────────────────

def run_kg_builder(
    input_path: Path,
    output_dir: Path,
) -> Optional[Path]:
    from graph.kg_builder import build_knowledge_graph, graph_to_json, build_summary
    out = output_dir / "kg.json"
    try:
        G       = build_knowledge_graph(input_path)
        summary = build_summary(G)
        out.write_text(
            json.dumps(graph_to_json(G), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (output_dir / "kg_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(
            "KG: %d nodes, %d edges, %d high-risk libs",
            summary["total_nodes"],
            summary["total_edges"],
            len(summary["high_risk_libraries"]),
        )
        return out
    except Exception as e:
        logger.error("kg_builder failed: %s", e, exc_info=True)
        return None


# ── Stage 7: Contradiction detector ──────────────────────────────────────────

def run_contradiction_detector(
    data_root: Path,
) -> Optional[Path]:
    from reasoning.contradiction_detector import ProprietaryContradictionDetector
    try:
        # Pass data/processed/ directly — detector reads/writes inside that folder
        detector = ProprietaryContradictionDetector(data_root / "processed")
        detector.detect_proprietary_mismatches()
        output_path = data_root / "processed" / "contradiction_evidence.json"
        return output_path if output_path.exists() else None
    except Exception as e:
        logger.error("contradiction_detector failed: %s", e, exc_info=True)
        return None


# ── Stage 8: Hop reasoner ─────────────────────────────────────────────────────

def run_hop_reasoner(
    kg_path:    Path,
    output_dir: Path,
    max_hops:   int   = 3,
    threshold:  float = 0.28,
) -> Optional[Path]:
    from reasoning.hop_reasoner import load_graph, reason, save_chains
    out = output_dir / "hop_chains.json"
    try:
        G      = load_graph(kg_path)
        chains = reason(G, max_hops=max_hops, chain_threshold=threshold)
        save_chains(chains, out)
        logger.info(
            "Hop reasoner: %d chains, %d with licence conflict, %d with patent",
            len(chains),
            sum(1 for c in chains if c.has_licence_conflict),
            sum(1 for c in chains if c.has_patent_node),
        )
        return out
    except Exception as e:
        logger.error("hop_reasoner failed: %s", e, exc_info=True)
        return None


# ── Stage 9: Question generation ──────────────────────────────────────────────

def run_question_gen(
    chains_path:   Path,
    output_dir:    Path,
    dry_run:       bool          = False,
    max_questions: Optional[int] = None,
    backend:       str           = "ollama",
    model:         str           = "phi3",
) -> Optional[Path]:
    out = output_dir / "questions.json"
    try:
        from generation.question_gen import generate_questions, save_questions, print_questions
        questions = generate_questions(
            chains_path   = chains_path,
            output_path   = out,
            backend       = backend,
            model         = model,
            dry_run       = dry_run,
            max_questions = max_questions,
        )
        print_questions(questions)
        save_questions(questions, out)
        logger.info("Question gen: %d questions (%s/%s)", len(questions), backend, model)
        return out
    except Exception as e:
        logger.error("question_gen failed: %s", e, exc_info=True)
        return None


# ── Stage 10: Explainability engine ───────────────────────────────────────────

def run_explainability_engine(
    data_root: Path,
) -> Optional[Path]:
    from audit.explainability_engine import EvidenceAuditLayer
    try:
        engine = EvidenceAuditLayer(data_root)
        engine.build_audit_trail(source_filename="questions.json")
        output_path = data_root / "processed" / "audited_vc_report.json"
        return output_path if output_path.exists() else None
    except Exception as e:
        logger.error("explainability_engine failed: %s", e, exc_info=True)
        return None


# ── Pipeline eval harness ─────────────────────────────────────────────────────

def run_eval(questions_path: Path, ground_truth_path: Optional[Path]) -> dict:
    questions_data = json.loads(questions_path.read_text(encoding="utf-8"))
    questions      = questions_data.get("questions", [])

    results = {
        "total_questions":             len(questions),
        "questions_with_audit_trail":  sum(1 for q in questions if q.get("audit_trail")),
        "questions_with_licence_flag": sum(1 for q in questions if q.get("has_licence_conflict")),
        "questions_with_patent_flag":  sum(1 for q in questions if q.get("has_patent_node")),
        "category_breakdown":          {},
    }

    for q in questions:
        cat = q.get("question_category", "unknown")
        results["category_breakdown"][cat] = results["category_breakdown"].get(cat, 0) + 1

    results["phase1_pass"] = (
        results["questions_with_audit_trail"] == results["total_questions"]
        and results["total_questions"] > 0
    )

    if ground_truth_path and ground_truth_path.exists():
        gt            = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        gt_questions  = [q["question"].lower() for q in gt.get("questions", [])]
        gen_questions = [q["question"].lower() for q in questions]
        overlap_count = 0
        for gen_q in gen_questions:
            gen_words = set(w for w in gen_q.split() if len(w) >= 4)
            for gt_q in gt_questions:
                gt_words = set(w for w in gt_q.split() if len(w) >= 4)
                if len(gen_words & gt_words) >= 2:
                    overlap_count += 1
                    break
        results["ground_truth_overlap"] = overlap_count / max(len(gen_questions), 1)

    return results


def print_eval(results: dict):
    print(f"\n{'='*60}")
    print("  PIPELINE EVAL RESULTS")
    print(f"{'='*60}")
    print(f"  Total questions generated  : {results['total_questions']}")
    print(f"  With audit trail           : {results['questions_with_audit_trail']}")
    print(f"  With licence flag          : {results['questions_with_licence_flag']}")
    print(f"  With patent flag           : {results['questions_with_patent_flag']}")
    print(f"\n  Category breakdown:")
    for cat, count in results.get("category_breakdown", {}).items():
        print(f"     {cat:<25} {count}")
    if "ground_truth_overlap" in results:
        print(f"\n  Ground truth overlap       : {results['ground_truth_overlap']:.2%}")
    status = "[PASS]" if results.get("phase1_pass") else "[FAIL]"
    print(f"\n  Phase 1 check (all questions have audit trail): {status}")
    print(f"{'='*60}\n")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(args: argparse.Namespace) -> bool:
    timer      = StageTimer()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    whitepaper_path = Path(args.whitepaper)
    repo_path       = Path(args.repo)         if args.repo         else None
    patents_path    = Path(args.patents)       if args.patents      else None
    gt_path         = Path(args.ground_truth) if args.ground_truth else None

    whitepaper_json: Optional[Path] = None
    codebase_json:   Optional[Path] = None
    patent_json:     Optional[Path] = None
    matches_json:    Optional[Path] = None
    kg_json:         Optional[Path] = None
    chains_json:     Optional[Path] = None

    data_root = (
        Path(args.output).parent
        if Path(args.output).name == "processed"
        else Path(args.output)
    )

    # ── Stage 1 ───────────────────────────────────────────────────────────────
    timer.start("1_whitepaper_parser")
    whitepaper_json = run_whitepaper_parser(
        whitepaper_path, output_dir, force_ocr=args.ocr
    )
    timer.stop()
    if not whitepaper_json:
        logger.error("Pipeline aborted: whitepaper_parser failed")
        return False

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    if repo_path and repo_path.exists():
        timer.start("2_github_parser")
        codebase_json = run_github_parser(repo_path, output_dir)
        timer.stop()
    else:
        logger.warning("No --repo provided or path doesn't exist — skipping github_parser")
        codebase_json = output_dir / "codebase_knowledge.json"
        codebase_json.write_text(
            json.dumps({
                "dependency_map":         {"all_dependencies": []},
                "import_graph_analysis":  {"top_third_party_libraries": []},
                "import_graph_structure": {"nodes": [], "edges": []},
            }, indent=2),
            encoding="utf-8",
        )

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    if patents_path and patents_path.exists():
        timer.start("3_patent_parser")
        patent_json = run_patent_parser(patents_path, output_dir)
        timer.stop()
    else:
        logger.warning("No --patents provided or path doesn't exist — skipping patent_parser")
        patent_json = output_dir / "knowledge_base.json"
        patent_json.write_text(
            json.dumps({"metadata": {"total_triples": 0}, "triples": []}, indent=2),
            encoding="utf-8",
        )

    # ── Stage 4 ───────────────────────────────────────────────────────────────
    timer.start("4_knowledge_fusion")
    fused_path = run_knowledge_fusion(data_root, threshold=args.fusion_threshold)
    timer.stop()
    if not fused_path:
        logger.warning("Knowledge fusion failed — continuing with raw parser outputs only.")

    # ── Stage 5 ───────────────────────────────────────────────────────────────
    timer.start("5_entity_resolver")
    matches_json = run_entity_resolver(
        whitepaper_json = whitepaper_json,
        codebase_json   = codebase_json,
        patent_json     = patent_json,
        output_dir      = output_dir,
        threshold       = args.resolver_threshold,
    )
    timer.stop()
    if not matches_json and not fused_path:
        logger.error("Pipeline aborted: entity_resolver failed and no fused graph available")
        return False

    # ── Stage 6 ───────────────────────────────────────────────────────────────
    timer.start("6_kg_builder")
    kg_input_path = (
        fused_path
        if fused_path and fused_path.exists()
        else matches_json
    )
    kg_json = run_kg_builder(kg_input_path, output_dir)
    timer.stop()
    if not kg_json:
        logger.error("Pipeline aborted: kg_builder failed")
        return False

    # ── Stage 7 ───────────────────────────────────────────────────────────────
    timer.start("7_contradiction_detector")
    contradiction_json = run_contradiction_detector(data_root)
    timer.stop()
    if not contradiction_json:
        logger.warning("Contradiction detector: no proprietary mismatches found.")

    # ── Stage 8 ───────────────────────────────────────────────────────────────
    timer.start("8_hop_reasoner")
    chains_json = run_hop_reasoner(
        kg_path    = kg_json,
        output_dir = output_dir,
        max_hops   = args.max_hops,
        threshold  = args.chain_threshold,
    )
    timer.stop()
    if not chains_json:
        logger.error("Pipeline aborted: hop_reasoner failed")
        return False

    # ── Stage 9 ───────────────────────────────────────────────────────────────
    timer.start("9_question_gen")
    questions_json = run_question_gen(
        chains_path   = chains_json,
        output_dir    = output_dir,
        dry_run       = args.dry_run,
        max_questions = args.max_questions,
        backend       = args.backend,
        model         = args.model,
    )
    timer.stop()
    if not questions_json:
        logger.error("Pipeline aborted: question_gen failed")
        return False

    # ── Stage 10 ──────────────────────────────────────────────────────────────
    timer.start("10_explainability_engine")
    audit_json = run_explainability_engine(data_root)
    timer.stop()
    if audit_json:
        logger.info("Audit trail written → %s", audit_json)
    else:
        logger.warning("Explainability engine produced no audit report.")

    # ── Timing report ─────────────────────────────────────────────────────────
    timer.print_report()
    timing_path = output_dir / "pipeline_timing.json"
    timing_path.write_text(json.dumps(timer.report(), indent=2), encoding="utf-8")

    # ── Eval harness ──────────────────────────────────────────────────────────
    eval_results = run_eval(questions_json, gt_path)
    print_eval(eval_results)
    eval_path = output_dir / "eval_results.json"
    eval_path.write_text(json.dumps(eval_results, indent=2), encoding="utf-8")

    logger.info("Pipeline complete. All outputs in: %s", output_dir)
    logger.info("Primary deliverable  : %s", questions_json)
    logger.info("Audit trail          : %s", audit_json or "not generated")
    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end VC due-diligence pipeline orchestrator"
    )

    # ── Inputs ────────────────────────────────────────────────────────────────
    parser.add_argument("--whitepaper", "-w", required=True,
                        help="Path to startup whitepaper / pitch deck PDF")
    parser.add_argument("--repo",       "-r", default=None,
                        help="Path to startup code repository root (optional)")
    parser.add_argument("--patents",    "-p", default=None,
                        help="Path to directory of patent .txt files (optional)")
    parser.add_argument("--output",     "-o", default="data/processed/",
                        help="Output directory (default: data/processed/)")

    # ── Tuning ────────────────────────────────────────────────────────────────
    parser.add_argument("--resolver-threshold", type=float, default=0.45)
    parser.add_argument("--fusion-threshold",   type=float, default=0.40)
    parser.add_argument("--chain-threshold",    type=float, default=0.28)
    parser.add_argument("--max-hops",           type=int,   default=3)
    parser.add_argument("--max-questions",      type=int,   default=None)

    # ── LLM backend ───────────────────────────────────────────────────────────
    parser.add_argument("--backend", choices=["ollama", "anthropic"], default="ollama",
                        help="LLM backend (default: ollama)")
    parser.add_argument("--model", default="phi3",
                        help="Ollama model name (default: phi3)")

    # ── Flags ─────────────────────────────────────────────────────────────────
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--ground-truth", default=None)
    parser.add_argument("--ocr",          action="store_true")

    args    = parser.parse_args()
    success = run_pipeline(args)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()