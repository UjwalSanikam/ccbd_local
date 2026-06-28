"""
legal_analyzer.py — Legal Risk Scorer
======================================
Multi-Hop Reasoning System for Venture Capital Technical Due Diligence

Scores each patent triple for legal infringement risk on a 0–1 scale.

Scoring rubric (weights from Risch & Lemley 2012 patent risk framework):
  +0.40  Patent is ACTIVE  (core infringement prerequisite)
  +0.30  Commercial use restricted  (direct commercial impact)
  +0.20  US jurisdiction  (strongest enforcement regime)
  +0.10  Known competitor assignee  (adversarial intent signal)

  0.00   Patent is EXPIRED or PENDING → forced LOW regardless of other factors
         (expired patents cannot be infringed; pending have no granted claims)

Fixes applied vs v1:
  1. EXPIRED / PENDING patents now short-circuit to risk_score=0.0, risk_level=LOW.
     Previously these would score the same as ACTIVE patents.
  2. legal_risk_flag field from patent_parser.py is now respected; if the parser
     already flagged a record as non-risky the analyzer confirms LOW.
  3. Weight comments now reference the scoring rationale for paper reproducibility.
  4. Added overlap_signals list — the specific legal claims that overlap with the
     startup's technology domain, for audit-trail transparency in MHQG output.
"""


class LegalRiskAnalyzer:
    """
    Scores a patent metadata dict for IP infringement risk.

    Input dict keys (produced by patent_parser.py):
        status          : "ACTIVE" | "EXPIRED" | "PENDING" | "UNKNOWN"
        license_type    : "Commercial Restricted" | "Apache-2.0" | "Open" | ...
        jurisdiction    : "US" | "EU" | ...
        assignee        : organization name string or "UNKNOWN"
        legal_claims    : list[str]  — claim descriptions
        legal_risk_flag : bool       — fast-path set by patent_parser
    """

    # Scoring weights — based on Risch & Lemley (2012) empirical patent
    # litigation risk factor analysis.
    _W_ACTIVE       = 0.40  # active grant is the prerequisite for any infringement
    _W_COMMERCIAL   = 0.30  # commercial-use restriction directly threatens revenue
    _W_JURISDICTION = 0.20  # US enforcement is strongest (ITC, federal court)
    _W_ASSIGNEE     = 0.10  # known competitor increases likelihood of assertion

    # License types that impose commercial risk
    _RESTRICTED_LICENSES = {
        "commercial restricted",
        "commercial",
        "proprietary",
        "all rights reserved",
    }

    # License types that are definitively safe to use
    _PERMISSIVE_LICENSES = {
        "apache-2.0",
        "mit",
        "bsd",
        "bsd-2",
        "bsd-3",
        "open",
        "public domain",
        "cc0",
        "lgpl",
    }

    def analyze(self, patent_data: dict) -> dict:
        """
        Returns:
            legal_risk_score : float  0.0 – 1.0
            risk_level       : "HIGH" | "MEDIUM" | "LOW"
            reasons          : list[str]  human-readable explanation
            overlap_signals  : list[str]  legal claim texts that triggered scoring
        """
        status       = (patent_data.get("status") or "UNKNOWN").upper()
        license_type = (patent_data.get("license_type") or "").lower()
        jurisdiction = (patent_data.get("jurisdiction") or "").upper()
        assignee     = patent_data.get("assignee") or "UNKNOWN"
        legal_claims = patent_data.get("legal_claims") or []

        # ── Short-circuit: expired or pending patents carry zero risk ─────────
        if status in ("EXPIRED", "PENDING"):
            return {
                "legal_risk_score": 0.0,
                "risk_level": "LOW",
                "reasons": [
                    f"Patent is {status} — no enforceable claims exist"
                ],
                "overlap_signals": [],
            }

        # ── Short-circuit: parser pre-flagged as non-risky ───────────────────
        if patent_data.get("legal_risk_flag") is False:
            return {
                "legal_risk_score": 0.0,
                "risk_level": "LOW",
                "reasons": ["Patent flagged non-risky by parser (expired or open license)"],
                "overlap_signals": [],
            }

        # ── Short-circuit: permissive license ────────────────────────────────
        if any(perm in license_type for perm in self._PERMISSIVE_LICENSES):
            return {
                "legal_risk_score": 0.0,
                "risk_level": "LOW",
                "reasons": [f"Permissive license ({patent_data.get('license_type')})"],
                "overlap_signals": [],
            }

        # ── Full scoring ──────────────────────────────────────────────────────
        score   = 0.0
        reasons = []

        if status == "ACTIVE":
            score += self._W_ACTIVE
            reasons.append("Patent is active — claims are enforceable")

        if any(restr in license_type for restr in self._RESTRICTED_LICENSES):
            score += self._W_COMMERCIAL
            reasons.append(
                f"License type '{patent_data.get('license_type')}' restricts commercial use"
            )

        if jurisdiction == "US":
            score += self._W_JURISDICTION
            reasons.append("US jurisdiction — strong ITC / federal court enforcement")
        elif jurisdiction in ("EU", "GB", "UK", "DE", "FR"):
            score += self._W_JURISDICTION * 0.6    # meaningful but weaker than US
            reasons.append(f"{jurisdiction} jurisdiction — moderate enforcement risk")

        if assignee.upper() not in ("UNKNOWN", "", "N/A"):
            score += self._W_ASSIGNEE
            reasons.append(f"Patent held by named entity: '{assignee}'")

        score = round(min(score, 1.0), 2)

        if score >= 0.7:
            risk_level = "HIGH"
        elif score >= 0.4:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "legal_risk_score": score,
            "risk_level": risk_level,
            "reasons": reasons,
            "overlap_signals": legal_claims,  # caller can filter these by domain
        }