import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# A simulated Open-Source License Database for your Big Data pipeline
LICENSE_DB = {
    "os": "PSF-2.0 (Permissive - Safe)",
    "json": "PSF-2.0 (Permissive - Safe)",
    "networkx": "BSD-3-Clause (Permissive - Safe)",
    "pydantic": "MIT (Permissive - Safe)",
    "hashlib": "PSF-2.0 (Permissive - Safe)",
    "cryptography": "Apache-2.0 (Permissive - Safe)",
    "pycryptodome": "BSD-2-Clause (Permissive - Safe)",
    "flask": "BSD-3-Clause (Permissive - Safe)",
    "django": "BSD-3-Clause (Permissive - Safe)",
    "numpy": "BSD-3-Clause (Permissive - Safe)",
    "pandas": "BSD-3-Clause (Permissive - Safe)",
    "scikit-learn": "BSD-3-Clause (Permissive - Safe)",
    "tensorflow": "Apache-2.0 (Permissive - Safe)",
    "torch": "BSD-3-Clause (Permissive - Safe)",
    "transformers": "Apache-2.0 (Permissive - Safe)",
    "sentence-transformers": "Apache-2.0 (Permissive - Safe)",
    "faiss": "MIT (Permissive - Safe)",
    "openai": "MIT (Permissive - Safe)",
    "anthropic": "MIT (Permissive - Safe)",
    "train": "MIT (Permissive - Safe)",
    "grpcio": "Apache-2.0 (Permissive - Safe)",
    "sqlalchemy": "MIT (Permissive - Safe)",
    "requests": "Apache-2.0 (Permissive - Safe)",
    "pytest": "MIT (Permissive - Safe)",
    "neo4j": "GPL-3.0 (Strict Copyleft - 🚨 HIGH VC RISK!)",
    "py2neo": "Apache-2.0 (Permissive - Safe)",
    "redis": "BSD-3-Clause (Permissive - Safe)",
    "boto3": "Apache-2.0 (Permissive - Safe)",
    "spacy": "MIT (Permissive - Safe)",
    "langchain": "MIT (Permissive - Safe)",
}

RISK_MAP = {
    "MIT": "low",
    "Apache-2.0": "low",
    "BSD-3-Clause": "low",
    "BSD-2-Clause": "low",
    "PSF-2.0": "low",
    "MPL-2.0": "low",
    "LGPL-2.1": "medium",
    "LGPL-3.0": "medium",
    "GPL-2.0": "high",
    "GPL-3.0": "high",
    "AGPL-3.0": "high",
    "SSPL": "high",
    "CC-BY-NC": "high",
    "CC-BY-NC-SA": "high",
}

def run_license_scan(data_dir: Path):
    logger.info("Starting Track 4: Open-Source License Intelligence Scan...")
    
    code_path = data_dir / "processed" / "codebase_knowledge.json"
    if not code_path.exists():
        logger.error("codebase_knowledge.json not found! Run github_parser.py first.")
        return

    code_data = json.loads(code_path.read_text(encoding="utf-8"))
    nodes = code_data.get("import_graph_structure", {}).get("nodes", [])

    license_triples = []
    
    for node in nodes:
        module_name = node["id"]
        # We only scan external third-party libraries for licenses, not internal code
        if node.get("type") == "internal":
            continue 

        raw_license = LICENSE_DB.get(module_name.lower()) or LICENSE_DB.get(module_name) or "UNKNOWN"
        if raw_license == "UNKNOWN":
            license_name = "UNKNOWN (Requires Manual Review ⚠️)"
            risk = "unknown"
            spdx = "UNKNOWN"
        else:
            license_name = raw_license
            spdx = raw_license.split()[0].upper()
            risk = RISK_MAP.get(spdx, "unknown")

        license_triples.append({
            "module": module_name,
            "relationship": "LICENSED_UNDER",
            "license": license_name,
            "risk": risk,
            "commercial_use": risk != "low",
            "copyleft": spdx in {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "SSPL"},
        })
        logger.info(f"Scanned Dependency: '{module_name}' -> Licensed under: {license_name}")

    output_path = data_dir / "processed" / "license_knowledge.json"
    output_path.write_text(json.dumps({"licenses": license_triples}, indent=2), encoding="utf-8")
    logger.info(f"Track 4 License Data saved to → {output_path}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    run_license_scan(project_root / "data")