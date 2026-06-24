import json
import logging
import hashlib
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class EvidenceAuditLayer:
    """
    V4.0 Evidence Audit Layer: Ensures every generated risk is traceable 
    and mathematically verifiable for boardroom-level due diligence.
    """
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _generate_trace_id(self, evidence_string: str) -> str:
        return hashlib.sha256(evidence_string.encode()).hexdigest()[:12].upper()

    def build_audit_trail(self):
        logger.info("Initializing Evidence Audit Layer...")
        
        report_path = self.data_dir / "processed" / "vc_risk_report.json"
        if not report_path.exists():
            logger.error("vc_risk_report.json not found!")
            return
            
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        risks = report_data.get("identified_risks", [])
        
        audited_risks = []
        
        for risk in risks:
            chain = risk["evidence_chain"]
            category = risk["category"]
            confidence = risk["confidence_score"] # Using the new Confidence Engine math!
            
            trace_id = f"TRC-{self._generate_trace_id(chain)}-{int(time.time())}"
                
            audit_object = {
                "traceability_id": trace_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "severity": risk["severity"],
                "category": category,
                "target_entity": risk["target_entity"],
                "formal_confidence": confidence,
                "recommended_action": risk["recommended_action"],
                "evidence_chain": chain,
                "audit_status": "MACHINE_ASSISTED_VERIFICATION"
            }
            audited_risks.append(audit_object)
            
        output_path = self.data_dir / "processed" / "audited_vc_report.json"
        output_path.write_text(json.dumps({"audited_risks": audited_risks}, indent=2), encoding="utf-8")
        logger.info(f"Generated Audit Trail for {len(audited_risks)} risks (Status: MACHINE_ASSISTED_VERIFICATION).")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    engine = EvidenceAuditLayer(project_root / "data")
    engine.build_audit_trail()