import json
import logging
import requests
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class EnterpriseVCInterrogator:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _ollama_llm_call(self, system_prompt: str, evidence: str) -> str:
        prompt = f"{system_prompt}\n\nAUDITABLE EVIDENCE SUMMARY:\n{evidence}\n\nQUESTION:"
        payload = {
            "model": "phi3",
            "prompt": prompt,
            "stream": False
        }
        try:
            response = requests.post("http://localhost:11434/api/generate", json=payload)
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            return f"🚨 OLLAMA ERROR: {str(e)}"

    def generate_boardroom_questions(self):
        logger.info("\n" + "="*80)
        logger.info("🚀 EXECUTING AUDITED GRAPHRAG (PHI-3) BOARDROOM INTERROGATION")
        logger.info("="*80 + "\n")

        report_path = self.data_dir / "processed" / "audited_vc_report.json"
        if not report_path.exists():
            logger.error("audited_vc_report.json not found.")
            return

        data = json.loads(report_path.read_text(encoding="utf-8"))
        risks = data.get("audited_risks", [])

        if not risks:
            logger.info("✅ No actionable risks found. Startup passes technical due diligence.")
            return

        for risk in risks:
            evidence_chain = risk["evidence_chain"]
            severity = risk["severity"]
            category = risk["category"]
            target = risk["target_entity"]
            trace_id = risk["traceability_id"]
            confidence = risk["formal_confidence"]
            
            sys_prompt = ""
            
            if category == "IP Overlap":
                sys_prompt = (
                    "You are a professional Venture Capital Analyst. Review the evidence summary below. "
                    "Our graph retrieval system has flagged a potential area requiring further technical review due to semantic overlap "
                    "with existing technologies. Generate ONE highly professional, objective due-diligence question asking the founders "
                    "about their commercialization strategy and how they manage potential overlap with existing technologies. Do NOT suggest infringement or make legal accusations."
                )
            elif category == "Commercial License":
                sys_prompt = (
                    "You are a professional Venture Capital Analyst. Review the evidence summary below. "
                    "Our architecture scan found that the startup's code utilizes open-source licenses with potential commercial constraints. "
                    "Generate ONE highly professional, objective due-diligence question asking the founders about their open-source compliance strategy "
                    "and how they plan to manage dependency risk as they scale."
                )
            elif category == "Proprietary Claim Mismatch":
                sys_prompt = (
                    "You are a professional Venture Capital Analyst. Review the evidence summary below. "
                    "Our architecture scan noted a discrepancy between the startup's marketing claims regarding proprietary technology, "
                    "and their usage of standard open-source libraries. Generate ONE highly professional, objective due-diligence "
                    "question asking the founders to clarify their core technical differentiation."
                )
            else:
                continue

            print(f"🧠 [Phi-3] Formulating inquiry for {trace_id} ({category})...")
            llm_question = self._ollama_llm_call(sys_prompt, evidence_chain)

            icon = "🛡️" if severity in ["MODERATE", "LOW"] else "⚠️"
            print(f"\n{icon} [{severity}] {category.upper()} - AREA FOR REVIEW")
            print(f"  [Traceability ID] : {trace_id} (Calculated Confidence: {confidence * 100}%)")
            print(f"  [Target Entity]   : {target}")
            print(f"  [Phi-3 Output]    : {llm_question}\n")
            print("-" * 80 + "\n")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    engine = EnterpriseVCInterrogator(project_root / "data")
    engine.generate_boardroom_questions()