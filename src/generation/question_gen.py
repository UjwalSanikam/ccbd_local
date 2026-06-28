"""
question_gen.py — Adversarial Question Generator
=================================================
Multi-Hop Reasoning System for VC Technical Due Diligence

Takes hop_chains.json (from hop_reasoner.py) and calls an LLM to generate
one pointed, adversarial due-diligence question per chain. Every question
is returned with its full provenance audit trail.

LLM backends (in priority order):
  1. Ollama (local)      — default, no API key needed
                           install: https://ollama.com
                           model:   ollama pull llama3.2
  2. Anthropic Claude    — used only if ANTHROPIC_API_KEY env var is set
                           and --backend anthropic is passed
  3. Dry-run             -- prints prompts, no LLM call

Output:
    data/processed/questions.json

Usage:
    # Ollama (default — no API key needed)
    python src/generation/question_gen.py

    # Dry run (no LLM at all)
    python src/generation/question_gen.py --dry-run

    # Anthropic Claude (optional)
    export ANTHROPIC_API_KEY=your_key_here
    python src/generation/question_gen.py --backend anthropic

    # Different Ollama model
    python src/generation/question_gen.py --model mistral
"""

import os
import json
import logging
import argparse
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_OLLAMA_MODEL   = "llama3.2"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
OLLAMA_BASE_URL        = "http://localhost:11434"
MAX_TOKENS             = 150  # one-sentence question — 512 was wasting CPU time and inviting prompt leaks
RETRY_ATTEMPTS         = 3
RETRY_DELAY            = 2.0
RATE_LIMIT_DELAY       = 0.3   # shorter for local model

SYSTEM_PROMPT = """You are a senior technical due-diligence analyst at a venture capital firm.
Your job is to generate sharp, specific, adversarial questions that a VC partner should ask
a startup founder during a technical review meeting.

Rules:
- Output ONLY the question. No preamble, no "Here is a question", no explanation, no list.
- Ask exactly ONE question.
- The question must be grounded in the specific names, IDs, and facts given in the evidence
  chain below — never invent details that are not in the evidence.
- The question should be impossible to deflect with a vague answer. It should force the
  founder to either produce a specific artifact (a license, a freedom-to-operate opinion,
  a benchmark, a diff) or admit a gap.
- Tone: professional but pointed. A good question makes the founder pause.
- Do NOT ask generic questions like "How do you plan to scale?" or "What is your go-to-market
  strategy?" — those are not grounded in this evidence chain.
- End with a question mark.

QUALITY BAR — match this style (do not reuse the wording, these are illustrations only):
- Evidence: claim of a proprietary cryptographic module that maps to the standard "hashlib"
  library.
  Good question: "Your whitepaper describes a proprietary cryptographic hashing module, but
  the codebase calls Python's standard hashlib library for this function — what specifically
  have you built on top of hashlib that justifies calling it proprietary, and can you show us
  the diff?"
- Evidence: a library used in the codebase maps to an ACTIVE patent held by a named competitor,
  flagged as legal risk.
  Good question: "Patent US11456789, held by CompetitorX Inc. and currently active, covers
  cryptographic token verification that overlaps with how your codebase implements this
  feature — what freedom-to-operate analysis have you done, and do you have a license or
  non-infringement opinion on file?"
"""


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class GeneratedQuestion:
    question_id:          str
    chain_id:             str
    question:             str
    question_category:    str
    chain_score:          float
    hop_count:            int
    has_licence_conflict: bool
    has_patent_node:      bool
    audit_trail:          list[dict]
    raw_provenance:       dict
    backend_used:         str   # "ollama" | "anthropic" | "dry_run"
    quality_score:        int = 3

# ── Prompt builder ────────────────────────────────────────────────────────────

def _node_label(node: dict) -> str:
    """
    Human-readable label for a node.
    Claim nodes carry their actual whitepaper text in metadata — use that
    instead of the internal node_id (e.g. 'claim_0001'), which is meaningless
    to an LLM or a VC partner reading the question.
    """
    node_type = node.get("node_type", "Unknown")
    meta = node.get("metadata", {})

    if node_type == "Claim":
        text = (meta.get("text") or meta.get("full_text") or "").strip()
        if text:
            if len(text) > 220:
                text = text[:220].rsplit(" ", 1)[0] + "..."
            return text

    return node.get("node_id", node.get("label", "Unknown"))


def build_chain_summary(chain: dict) -> str:
    prov  = chain.get("provenance", {})
    nodes = prov.get("nodes", [])
    edges = prov.get("edges", [])
    lines = ["EVIDENCE CHAIN:"]

    for i, edge in enumerate(edges):
        from_node = next((n for n in nodes if n["node_id"] == edge["from"]), {})
        to_node   = next((n for n in nodes if n["node_id"] == edge["to"]),   {})

        from_type  = from_node.get("node_type", "Unknown")
        to_type    = to_node.get("node_type",   "Unknown")

        from_label = _node_label(from_node)
        to_label   = _node_label(to_node)

        edge_type = edge.get("edge_type", "relates_to")
        weight    = edge.get("weight", 0.0)

        from_meta = from_node.get("metadata", {})
        to_meta   = to_node.get("metadata",   {})

        hop_line = f"  Hop {i+1}: [{from_type}] \"{from_label}\""
        if from_type == "Claim":
            hop_line += f" (page={from_meta.get('page','?')})"
        elif from_type == "Library":
            licence = from_meta.get("licence") or from_meta.get("license")
            if licence:
                hop_line += f" (licence={licence}, risk={from_meta.get('licence_risk','?')})"
            elif from_meta.get("module_type"):
                hop_line += f" (module_type={from_meta.get('module_type')})"
        elif from_type == "Patent":
            hop_line += (
                f" (patent_id={from_meta.get('patent_id','?')}, "
                f"assignee={from_meta.get('assignee','?')}, "
                f"status={from_meta.get('status','?')}, risk={from_meta.get('risk','?')})"
            )
            if from_meta.get("legal_risk_flag"):
                hop_line += " [LEGAL RISK FLAGGED]"

        hop_line += f"\n        --[{edge_type} | similarity={weight:.2f}]-->" if weight is not None else f"\n        --[{edge_type}]-->"
        hop_line += f"\n        [{to_type}] \"{to_label}\""

        if to_type == "Library":
            licence = to_meta.get("licence") or to_meta.get("license")
            if licence:
                hop_line += f" (licence={licence}, risk={to_meta.get('licence_risk','?')})"
            elif to_meta.get("module_type"):
                hop_line += f" (module_type={to_meta.get('module_type')})"
        elif to_type == "Patent":
            hop_line += (
                f"\n        Patent details: id={to_meta.get('patent_id','?')}, "
                f"assignee={to_meta.get('assignee','?')}, jurisdiction={to_meta.get('jurisdiction','?')}, "
                f"status={to_meta.get('status','?')}, risk={to_meta.get('risk','?')}"
            )
            if to_meta.get("legal_risk_flag"):
                hop_line += " [LEGAL RISK FLAGGED]"
        elif to_type == "LicenceType":
            hop_line += f" (commercial_use_restricted={to_meta.get('commercial_use_restricted','?')})"

        lines.append(hop_line)

    lines.append(f"\nCHAIN CONFIDENCE SCORE: {chain.get('chain_score', 0.0):.4f}")

    flags = []
    if chain.get("has_licence_conflict"):
        flags.append("LICENCE CONFLICT DETECTED")
    if chain.get("has_patent_node"):
        flags.append("PATENT OVERLAP DETECTED")
    if flags:
        lines.append("FLAGS: " + " | ".join(flags))

    return "\n".join(lines)


def categorize_question(chain: dict) -> str:
    if chain.get("has_licence_conflict"):
        return "licence_risk"
    if chain.get("has_patent_node"):
        return "ip_conflict"
    edges = chain.get("path_edges", [])
    # NOTE: edge_type strings are e.g. "IMPLEMENTED_BY", "IMPORTS" — not "implements".
    # The old substring check here never matched, so every Claim->Library-only
    # chain (the majority of chains) silently fell through to "feasibility".
    if "IMPLEMENTED_BY" in edges:
        return "claim_contradiction"
    if "IMPORTS" in edges:
        return "dependency"
    return "feasibility"


_CATEGORY_FOCUS = {
    "ip_conflict": (
        "This chain links a marketing claim through a library to a PATENT. Write an "
        "adversarial question that forces the founder to address patent infringement or "
        "freedom-to-operate risk for this specific claim. Reference the patent's id, "
        "assignee, and status directly."
    ),
    "licence_risk": (
        "This chain reveals a licence conflict between a claim and a dependency's licence "
        "terms. Write an adversarial question about the legal and commercial exposure of "
        "shipping this dependency under its actual licence."
    ),
    "claim_contradiction": (
        "This chain shows a claim of proprietary or novel technology that maps directly to "
        "a named, ordinary library in the codebase. Write an adversarial question that "
        "challenges the 'proprietary' framing — ask what, concretely, is original versus a "
        "thin wrapper around that library, and demand evidence (a diff, a benchmark, a "
        "design doc)."
    ),
    "dependency": (
        "This chain shows a transitive dependency relationship between libraries. Write an "
        "adversarial question about hidden dependency risk, maintenance risk, or undisclosed "
        "third-party reliance implied by this chain."
    ),
    "feasibility": (
        "Write an adversarial due-diligence question about the technical feasibility of the "
        "claim, grounded specifically in this evidence chain."
    ),
}


def build_prompt(chain: dict) -> str:
    chain_summary = build_chain_summary(chain)
    category      = categorize_question(chain)
    focus         = _CATEGORY_FOCUS.get(category, _CATEGORY_FOCUS["feasibility"])

    return (
        "A startup's technical whitepaper has been cross-referenced against "
        "open-source dependency data and patent databases. "
        "The following evidence chain was discovered.\n\n"
        f"{chain_summary}\n\n"
        f"{focus}\n\n"
        "Output ONLY the question."
    )


# ── Audit trail ───────────────────────────────────────────────────────────────

def build_audit_trail(chain: dict) -> list[dict]:
    prov  = chain.get("provenance", {})
    nodes = prov.get("nodes", [])
    edges = prov.get("edges", [])
    trail = []

    for i, node in enumerate(nodes):
        step = {
            "step":      i + 1,
            "node_type": node.get("node_type"),
            "label":     _node_label(node),
            "metadata":  node.get("metadata", {}),
        }
        if i < len(edges):
            step["relationship_to_next"] = edges[i].get("edge_type")
            step["similarity_score"]     = edges[i].get("weight")
        trail.append(step)

    return trail


# ── Ollama backend ────────────────────────────────────────────────────────────

def _check_ollama_running() -> bool:
    """Check if Ollama server is reachable at localhost:11434."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _check_ollama_model(model: str) -> bool:
    """Check if the requested model is available in Ollama."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"].split(":")[0] for m in data.get("models", [])]
            return model in models
    except Exception:
        return False


def call_ollama(prompt: str, model: str = DEFAULT_OLLAMA_MODEL) -> Optional[str]:
    """
    Call Ollama's local REST API.
    Uses the /api/generate endpoint with stream=False for simplicity.
    """
    if not _check_ollama_running():
        logger.error(
            "Ollama is not running. Start it with: ollama serve\n"
            "Then pull a model: ollama pull %s", model
        )
        return None

    if not _check_ollama_model(model):
        logger.error(
            "Model '%s' not found in Ollama. Pull it with: ollama pull %s",
            model, model
        )
        return None

    payload = json.dumps({
        "model":  model,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": MAX_TOKENS,
            "temperature": 0.7,
        }
    }).encode("utf-8")

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/generate",
                data    = payload,
                headers = {"Content-Type": "application/json"},
                method  = "POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                text = data.get("response", "").strip()
                if text:
                    # ── Strip leaked prompt content ───────────────────────
                    # phi3 sometimes echoes back parts of the input prompt.
                    # Cut off at any of these known leak markers.
                    _leak_markers = [
                        "EVIDENCE CHAIN:",
                        "Based on this specific evidence",
                        "A startup's technical whitepaper",
                        "CHAIN CONFIDENCE SCORE:",
                        "Hop 1:",
                        "Hop 2:",
                        "Hop 3:",
                        "What if the original",
                        "As a follow up",
                        "Here are three more",
                    ]
                    for marker in _leak_markers:
                        if marker in text:
                            text = text[:text.index(marker)].strip()

                    # ── Strip common preambles phi3 adds before the question ──
                    _preamble_prefixes = [
                        "here is the question:", "here's the question:",
                        "question:", "sure,", "sure!", "certainly,",
                        "here is an adversarial question:",
                    ]
                    stripped_lower = text.lower()
                    for prefix in _preamble_prefixes:
                        if stripped_lower.startswith(prefix):
                            text = text[len(prefix):].strip()
                            stripped_lower = text.lower()

                    # Drop wrapping quote characters if the whole response is quoted
                    if len(text) > 1 and text[0] in "\"'" and text[-1] in "\"'":
                        text = text[1:-1].strip()

                    # Drop empty result after stripping
                    if not text:
                        logger.warning(
                            "Ollama response was entirely prompt echo on attempt %d",
                            attempt
                        )
                        continue

                    # Ensure question ends with a question mark
                    if not text.endswith("?"):
                        text = text.rstrip(".") + "?"

                    return text
                logger.warning("Ollama returned empty response on attempt %d", attempt)

        except urllib.error.URLError as e:
            logger.warning("Ollama call attempt %d/%d failed: %s", attempt, RETRY_ATTEMPTS, e)
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY * attempt)

    logger.error("All %d Ollama attempts failed", RETRY_ATTEMPTS)
    return None


# ── Anthropic backend ─────────────────────────────────────────────────────────

def call_anthropic(prompt: str, model: str = DEFAULT_ANTHROPIC_MODEL) -> Optional[str]:
    """
    Call the Anthropic Claude API.
    Only used if ANTHROPIC_API_KEY is set and --backend anthropic is passed.
    """
    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "anthropic package not found.\n"
            "Install: pip install anthropic\n"
            "Then:    export ANTHROPIC_API_KEY=your_key"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Run: $env:ANTHROPIC_API_KEY = 'your_key_here'"
        )

    client = anthropic.Anthropic(api_key=api_key)

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model      = model,
                max_tokens = MAX_TOKENS,
                system     = SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if not text.endswith("?"):
                text = text.rstrip(".") + "?"
            return text
        except Exception as e:
            logger.warning("Anthropic attempt %d/%d failed: %s", attempt, RETRY_ATTEMPTS, e)
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY * attempt)

    logger.error("All %d Anthropic attempts failed", RETRY_ATTEMPTS)
    return None


# ── Unified LLM caller ────────────────────────────────────────────────────────

def call_llm(
    prompt:   str,
    backend:  str  = "ollama",
    model:    str  = DEFAULT_OLLAMA_MODEL,
    dry_run:  bool = False,
) -> tuple[Optional[str], str]:
    """
    Route to the correct LLM backend.
    Returns (question_text, backend_used).
    """
    if dry_run:
        logger.info("[DRY RUN] Prompt:\n%s", prompt)
        return (
            "[DRY RUN] Given your claim of proprietary cryptographic technology, "
            "can you explain precisely which components are truly novel versus "
            "wrappers around open-source libraries detected in your codebase?",
            "dry_run",
        )

    if backend == "anthropic":
        text = call_anthropic(prompt, model=DEFAULT_ANTHROPIC_MODEL)
        return text, "anthropic"

    # Default: Ollama
    text = call_ollama(prompt, model=model)
    return text, "ollama"


# ── Main generator ────────────────────────────────────────────────────────────

def generate_questions(
    chains_path:   Path,
    output_path:   Path,
    backend:       str           = "ollama",
    model:         str           = DEFAULT_OLLAMA_MODEL,
    dry_run:       bool          = False,
    max_questions: Optional[int] = None,
) -> list[GeneratedQuestion]:
    data   = json.loads(chains_path.read_text(encoding="utf-8"))
    chains = data.get("chains", [])

    if max_questions:
        chains = chains[:max_questions]

    logger.info(
        "Generating %d questions using backend=%s model=%s",
        len(chains), "dry_run" if dry_run else backend, model
    )

    questions: list[GeneratedQuestion] = []
    q_counter = 0

    for i, chain in enumerate(chains):
        chain_id = chain.get("chain_id", f"chain_{i:04d}")
        logger.info(
            "[%d/%d] Processing %s (score=%.3f, hops=%d)",
            i + 1, len(chains),
            chain_id,
            chain.get("chain_score", 0),
            chain.get("hop_count", 0),
        )

        prompt             = build_prompt(chain)
        question, backend_used = call_llm(prompt, backend=backend, model=model, dry_run=dry_run)

        if question is None:
            logger.warning("Skipping %s — LLM call failed", chain_id)
            continue

        q_counter   += 1
        audit_trail  = build_audit_trail(chain)
        category     = categorize_question(chain)

        quality_score = 3  # default if dry_run or eval fails
        if not dry_run:
            chain_summary = build_chain_summary(chain)
            quality_score = self_evaluate_question(question, chain_summary, model)
            logger.info(
                "  Quality score: %d/5", quality_score
        )

        questions.append(GeneratedQuestion(
            question_id          = f"q_{q_counter:04d}",
            chain_id             = chain_id,
            question             = question,
            question_category    = category,
            chain_score          = chain.get("chain_score", 0.0),
            hop_count            = chain.get("hop_count", 0),
            has_licence_conflict = chain.get("has_licence_conflict", False),
            has_patent_node      = chain.get("has_patent_node", False),
            audit_trail          = audit_trail,
            raw_provenance       = chain.get("provenance", {}),
            backend_used         = backend_used,
            quality_score        = quality_score,
        ))

        if not dry_run and i < len(chains) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    logger.info("Generated %d questions from %d chains", len(questions), len(chains))
    return questions


# ── Output ────────────────────────────────────────────────────────────────────

def save_questions(questions: list[GeneratedQuestion], output_path: Path) -> None:
    by_category: dict[str, int] = {}
    by_backend:  dict[str, int] = {}
    for q in questions:
        by_category[q.question_category] = by_category.get(q.question_category, 0) + 1
        by_backend[q.backend_used]       = by_backend.get(q.backend_used, 0) + 1

    output = {
        "metadata": {
            "total_questions":         len(questions),
            "by_category":             by_category,
            "by_backend":              by_backend,
            "avg_quality_score":      round(sum(q.quality_score for q in questions) / max(len(questions), 1), 2),
            "licence_risk_questions":  sum(1 for q in questions if q.has_licence_conflict),
            "ip_conflict_questions":   sum(1 for q in questions if q.has_patent_node),
        },
        "questions": [asdict(q) for q in questions],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.info("Saved questions → %s", output_path)


def print_questions(questions: list[GeneratedQuestion]) -> None:
    print(f"\n{'='*72}")
    print("  GENERATED DUE-DILIGENCE QUESTIONS")
    print(f"{'='*72}")

    for q in questions:
        flags = []
        if q.has_licence_conflict:
            flags.append("[!] LICENCE")
        if q.has_patent_node:
            flags.append("[!] PATENT")
        flag_str = "  ".join(flags)

        print(f"\n  [{q.question_id}] {q.question_category.upper()}  {flag_str}")
        print(f"  Score: {q.chain_score:.4f}  |  Hops: {q.hop_count}  |  Chain: {q.chain_id}  |  Backend: {q.backend_used}  |  Quality: {q.quality_score}/5")
        print(f"\n  Q: {q.question}")
        print(f"\n  Audit trail:")
        for step in q.audit_trail:
            rel = f" --[{step.get('relationship_to_next')}]--> " if step.get("relationship_to_next") else ""
            print(f"     {step['step']}. [{step['node_type']}] {step['label']}{rel}")
        print(f"  {'-'*66}")

    print(f"\n{'='*72}\n")

def self_evaluate_question(question: str, chain_summary: str, model: str) -> int:
    eval_prompt = f"""Rate this due diligence question on a scale of 1-5:
1 = generic, could apply to any startup
5 = highly specific, references exact evidence, founder cannot deflect

Question: {question}
Evidence: {chain_summary[:200]}

Respond with only a single digit 1-5."""
    
    result = call_ollama(eval_prompt, model=model)
    try:
        return int(result.strip()[0])
    except:
        return 3

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate adversarial VC due-diligence questions from hop chains"
    )
    parser.add_argument("--chains",        default="data/processed/hop_chains.json")
    parser.add_argument("--output",        default="data/processed/questions.json")
    parser.add_argument(
        "--backend", choices=["ollama", "anthropic"], default="ollama",
        help="LLM backend to use (default: ollama)"
    )
    parser.add_argument(
        "--model", default=DEFAULT_OLLAMA_MODEL,
        help=f"Model name for Ollama (default: {DEFAULT_OLLAMA_MODEL}) or ignored for Anthropic"
    )
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--dry-run",       action="store_true")
    args = parser.parse_args()

    questions = generate_questions(
        chains_path   = Path(args.chains),
        output_path   = Path(args.output),
        backend       = args.backend,
        model         = args.model,
        dry_run       = args.dry_run,
        max_questions = args.max_questions,
    )
    print_questions(questions)
    save_questions(questions, Path(args.output))


if __name__ == "__main__":
    main()