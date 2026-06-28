import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class ConfidenceEngine:
    """
    Centralized Mathematical Engine for Venture Capital Risk Scoring.
    Calculates final confidence based on edge weights and applies path-length decay.
    """
    
    def __init__(self, base_decay_rate=0.90):
        # 10% penalty for every hop beyond the first direct connection
        self.decay_rate = base_decay_rate

    def compute_risk_metrics(self, category: str, path_length: int, base_similarity: float = 1.0):
        """
        Returns a tuple: (final_confidence_score, severity_level)
        """
        
        # 1. Determine Base Confidence Weight
        if category == "Commercial License":
            # Deterministic AST/File match. 100% certainty.
            base_score = 1.00
        elif category == "Proprietary Claim Mismatch":
            # Strong indicator of contradiction, but allows a tiny margin for context
            base_score = 0.95
        elif category == "IP Overlap":
            # Purely semantic. Relies exactly on the FAISS Cosine Similarity score.
            base_score = base_similarity
        else:
            base_score = 0.50 # Unknown category fallback

        # 2. Apply Multi-Hop Decay Penalty
        # Path length of 1 edge (Claim -> Code) gets no penalty. 
        # Path length of 3 edges (Claim -> Code -> Dep -> License) gets penalized twice.
        penalty_hops = max(0, path_length - 1)
        decay_multiplier = self.decay_rate ** penalty_hops
        
        final_confidence = round(base_score * decay_multiplier, 3)

        # 3. Dynamic Severity Threshold Mapping
        severity = self._map_severity(final_confidence, category)
        
        return final_confidence, severity

    def _map_severity(self, confidence: float, category: str) -> str:
        """
        Maps a mathematical percentage to a VC-standard categorical label.
        Overrides: Commercial Licenses are heavily weighted to Critical if confirmed.
        """
        if category == "Commercial License" and confidence >= 0.80:
            return "CRITICAL"
            
        if confidence >= 0.85:
            return "CRITICAL"
        elif confidence >= 0.65:
            return "HIGH"
        elif confidence >= 0.40:
            return "MODERATE"
        else:
            return "LOW"