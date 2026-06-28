# VC Due Diligence

A Multi-Hop VC Due Diligence System that reasons across pitch decks, GitHub codebases, and patent documents to generate adversarial due diligence questions for investors.

## Repository Structure

- `data/raw/` — input pitch decks, repositories, and patent text files
- `data/processed/` — generated JSON outputs and intermediate artifacts
- `src/extractors/` — parser modules for whitepapers, GitHub repositories, and patents
- `src/parsers/` — license intelligence module
- `src/graph/` — knowledge fusion and graph builder
- `src/resolvers/` — cross-domain entity resolution
- `src/reasoning/` — contradiction detection, multi-hop reasoning, and fallback question generation
- `src/scoring/` — confidence engine
- `src/audit/` — explainability and audit trail generation
- `src/generation/` — primary Claude-based question generator
- `scripts/` — helper scripts for patent download and retrieval
- `tests/` — smoke tests

## Setup

1. Create a Python environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. (Optional) Set your Anthropic API key for primary question generation:

```powershell
$env:ANTHROPIC_API_KEY = "your_key_here"
```

## Running the Full Pipeline

From the repository root:

```powershell
python src/pipeline.py \
  --whitepaper data/raw/<startup>_pitch.pdf \
  --repo data/raw/<startup>_repo \
  --patents data/raw/patents \
  --output data/processed/ \
  --fusion-threshold 0.40 \
  --resolver-threshold 0.45 \
  --chain-threshold 0.28
```

The pipeline produces:

- `data/processed/whitepaper_parsed.json`
- `data/processed/codebase_knowledge.json`
- `data/processed/knowledge_base.json`
- `data/processed/entity_matches.json`
- `data/processed/kg.json`
- `data/processed/hop_chains.json`
- `data/processed/questions.json`
- `data/processed/audited_vc_report.json`
- `data/processed/pipeline_timing.json`
- `data/processed/eval_results.json`

## Primary / Fallback Behavior

- Primary question generation uses `src/generation/question_gen.py` with Anthropic Claude.
- If `ANTHROPIC_API_KEY` is not set or the API cannot be called, the pipeline falls back to `src/reasoning/mhqg_engine.py`.

## Notes

- `knowledge_fusion.py` now exports `fused_knowledge_graph.json` with both `links` and `edges` keys and dual node labels (`label` and `node_type`).
- `kg_builder.py` supports both `entity_matches.json` and fused JSON graph inputs.
- `contradiction_detector.py` now uses `confidence_engine.py` instead of hardcoded scores.
- `explainability_engine.py` emits SHA-256 audit trace IDs and consumes generated questions for audit output.
- `license_parser.py` includes an expanded license database and risk classification.

## Testing

```powershell
pytest tests
```

## Troubleshooting

- If the pipeline stops at the knowledge fusion stage, ensure the `data/processed/` inputs exist and are valid JSON.
- If question generation falls back to MHQG, it means the Anthropic API key was unavailable.
- Use `--dry-run` with `src/pipeline.py` to skip the LLM call.
