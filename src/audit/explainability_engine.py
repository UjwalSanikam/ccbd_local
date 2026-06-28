import json
import logging
import hashlib
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class EvidenceAuditLayer:
    """
    V4.0 Evidence Audit Layer: Ensures every generated risk or question
    output is traceable and uses a SHA-256-based audit trail identifier.
    """
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _generate_trace_id(self, evidence_string: str) -> str:
        return hashlib.sha256(evidence_string.encode()).hexdigest()[:12].upper()

    def build_audit_trail(self, source_filename: str = "questions.json"):
        logger.info("Initializing Evidence Audit Layer...")
        
        report_path = self.data_dir / "processed" / source_filename
        if not report_path.exists():
            logger.error("Source report not found: %s", report_path)
            return
            
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        risks = report_data.get("questions", report_data.get("identified_risks", []))
        
        audited_items = []
        
        for item in risks:
            chain = item.get("raw_provenance") or item.get("evidence_chain") or {}
            category = item.get("question_category", item.get("category", "unknown"))
            confidence = item.get("chain_score", item.get("confidence_score", 0.0))
            question = item.get("question", item.get("generated_question", ""))
            target = item.get("target_claim") or item.get("target_entity")

            provenance_str = json.dumps(chain, sort_keys=True)
            trace_id = f"TRC-{self._generate_trace_id(provenance_str + question)}-{int(time.time())}"
                
            audit_object = {
                "traceability_id": trace_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "severity": item.get("risk_level", item.get("severity", "UNKNOWN")),
                "category": category,
                "target_entity": target,
                "question": question,
                "formal_confidence": confidence,
                "recommended_action": item.get("recommended_action", "Review the generated question and provenance for auditor follow-up."),
                "evidence_chain": chain,
                "audit_status": "MACHINE_ASSISTED_VERIFICATION"
            }
            audited_items.append(audit_object)
        
        output_path = self.data_dir / "processed" / "audited_vc_report.json"
        output_path.write_text(json.dumps({"audited_items": audited_items}, indent=2), encoding="utf-8")
        logger.info(f"Generated Audit Trail for %d items (Status: MACHINE_ASSISTED_VERIFICATION).", len(audited_items))

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    engine = EvidenceAuditLayer(project_root / "data")
    engine.build_audit_trail()