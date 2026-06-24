import sys
import json
import logging
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

# Now this import will work perfectly!
from confidence_engine import ConfidenceEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class RiskAnalyzer:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.confidence_engine = ConfidenceEngine()

    def analyze_evidence(self):
        logger.info("Initializing Formal Risk Taxonomy & Confidence Analysis...")
        
        analyzed_risks = []

        # --- 1. Load Path Reasoner Evidence (IP & Licenses) ---
        evidence_path = self.data_dir / "processed" / "structured_evidence.json"
        if evidence_path.exists():
            data = json.loads(evidence_path.read_text(encoding="utf-8"))
            for ev in data.get("evidence_objects", []):
                risk_node = ev["risk_node"]
                category = ev["risk_type"]
                path_length = ev["path_length"]
                raw_similarity = ev["confidence_score"]  # The FAISS score from path_reasoner
                path = ev["reasoning_path"]

                # Centralized Math Calculation!
                final_confidence, severity = self.confidence_engine.compute_risk_metrics(
                    category=category, 
                    path_length=path_length, 
                    base_similarity=raw_similarity
                )

                action_required = "Standard review."
                if category == "Commercial License" and severity == "CRITICAL":
                    action_required = "Immediate Legal Review: Codebase is tainted by strict obligations."
                elif category == "IP Overlap" and severity in ["HIGH", "MODERATE"]:
                    action_required = "Freedom-to-Operate (FTO) analysis required to review semantic overlap."

                if severity in ["CRITICAL", "HIGH", "MODERATE"]:
                    analyzed_risks.append({
                        "severity": severity,
                        "category": category,
                        "target_entity": risk_node,
                        "confidence_score": final_confidence,
                        "recommended_action": action_required,
                        "evidence_chain": " ➔ ".join(path)
                    })

        # --- 2. Load Contradiction Evidence (Startup Mismatches) ---
        contradiction_path = self.data_dir / "processed" / "contradiction_evidence.json"
        if contradiction_path.exists():
            logger.info("Scoring Proprietary Contradictions...")
            contra_data = json.loads(contradiction_path.read_text(encoding="utf-8"))
            for contra in contra_data.get("contradictions", []):
                
                # 1 Hop (Claim -> Code), no raw similarity needed
                final_confidence, severity = self.confidence_engine.compute_risk_metrics(
                    category=contra["risk_type"], 
                    path_length=1  
                )
                
                analyzed_risks.append({
                    "severity": severity,
                    "category": contra["risk_type"],
                    "target_entity": contra["contradictory_module"],
                    "confidence_score": final_confidence,
                    "recommended_action": "Technical Clarification: Require founders to explain the discrepancy.",
                    "evidence_chain": f"Marketing Pitch: '{contra['claim_text'][:50]}...' ➔ Review Indicator: '{contra['contradictory_module']}'"
                })

        output_path = self.data_dir / "processed" / "vc_risk_report.json"
        output_path.write_text(json.dumps({"identified_risks": analyzed_risks}, indent=2), encoding="utf-8")
        logger.info(f"Escalated {len(analyzed_risks)} actionable, mathematically-scored risks.")
        logger.info(f"Formal VC Risk Report saved to → {output_path}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    analyzer = RiskAnalyzer(project_root / "data")
    analyzer.analyze_evidence()