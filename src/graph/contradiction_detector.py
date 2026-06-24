import json
import logging
from pathlib import Path
import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# A simulated "Contradiction Taxonomy" used by VC Technical Auditors
# It maps "Proprietary Marketing Buzzwords" to the actual Open-Source libraries startups use to fake them.
CONTRADICTION_TAXONOMY = {
    "auth": {
        "marketing_triggers": ["proprietary authentication", "no open-source auth", "custom identity", "in-house auth"],
        "prohibited_imports": ["auth0", "okta", "flask_login", "passport", "jwt"]
    },
    "crypto": {
        "marketing_triggers": ["proprietary", "military-grade", "custom encryption", "in-house crypto", "secret lock"],
        "prohibited_imports": ["hashlib", "cryptography", "pycryptodome", "copyleft_crypto_engine"]
    },
    "database": {
        "marketing_triggers": ["custom ledger", "proprietary database", "in-house storage"],
        "prohibited_imports": ["sqlite3", "pymongo", "sqlalchemy", "redis"]
    }
}

class ProprietaryContradictionDetector:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.G = nx.DiGraph()
        self.load_graph()

    def load_graph(self):
        graph_path = self.data_dir / "processed" / "fused_knowledge_graph.json"
        if not graph_path.exists():
            logger.error("fused_knowledge_graph.json not found.")
            return
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            self.G.add_node(node["id"], **node)
        for edge in data.get("links", []):
            self.G.add_edge(edge["source"], edge["target"], **edge)

    def detect_proprietary_mismatches(self):
        logger.info("Initializing Proprietary Contradiction Engine...")
        
        claims = [n for n, d in self.G.nodes(data=True) if d.get("label") == "Marketing_Claim"]
        code_modules = [n for n, d in self.G.nodes(data=True) if d.get("label") == "Code_Module"]
        
        discovered_contradictions = []

        for claim in claims:
            claim_text = self.G.nodes[claim].get("full_text", "").lower()
            
            for category, taxonomy in CONTRADICTION_TAXONOMY.items():
                # Check if the startup is bragging about this specific category
                if any(trigger in claim_text for trigger in taxonomy["marketing_triggers"]):
                    
                    # If they are bragging, check the actual codebase for the prohibited open-source tools
                    for module in code_modules:
                        if any(prohibited in module.lower() for prohibited in taxonomy["prohibited_imports"]):
                            
                            logger.warning(f"🚨 CONTRADICTION CAUGHT: Claimed proprietary '{category}', but used '{module}'.")
                            
                            discovered_contradictions.append({
                                "risk_type": "Proprietary Claim Mismatch",
                                "severity": "HIGH",
                                "claim_id": claim,
                                "claim_text": self.G.nodes[claim].get("full_text", claim),
                                "contradictory_module": module,
                                "confidence_score": 0.99, # Deterministic codebase match
                                "recommended_action": f"Founder Interrogation: Demand explanation for why an open-source '{category}' library ({module}) is being marketed as proprietary IP."
                            })

        output_path = self.data_dir / "processed" / "contradiction_evidence.json"
        output_path.write_text(json.dumps({"contradictions": discovered_contradictions}, indent=2), encoding="utf-8")
        logger.info(f"Exported {len(discovered_contradictions)} Proprietary Contradictions to → {output_path}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    detector = ProprietaryContradictionDetector(project_root / "data")
    detector.detect_proprietary_mismatches()