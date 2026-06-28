import itertools
import json
import logging
from pathlib import Path
import networkx as nx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class DynamicPathReasoner:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.G = nx.DiGraph()
        self.load_graph()

    def load_graph(self):
        graph_path = self.data_dir / "processed" / "fused_knowledge_graph.json"
        if not graph_path.exists():
            logger.error("Fused graph not found. Run knowledge_fusion.py first.")
            return
            
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            self.G.add_node(node["id"], **node)
        for edge in data.get("links", []):
            self.G.add_edge(edge["source"], edge["target"], **edge)
            
        logger.info(f"Loaded Graph for Dynamic Traversal: {self.G.number_of_nodes()} nodes, {self.G.number_of_edges()} edges.")

    def calculate_path_confidence(self, path):
        """
        Calculates a confidence score based on the semantic similarity weights
        of the edges in the discovered path. Penalizes longer paths.
        """
        base_confidence = 1.0
        for i in range(len(path) - 1):
            source = path[i]
            target = path[i+1]
            edge_data = self.G.get_edge_data(source, target)
            
            # If it's a semantic edge, multiply by the similarity score.
            # If it's a structural edge (IMPORTS), assume high confidence (0.95).
            sim_score = edge_data.get("similarity", 0.95)
            base_confidence *= sim_score
            
        # Decay factor: Longer paths are inherently less confident
        length_penalty = 0.9 ** (len(path) - 2) 
        final_score = base_confidence * length_penalty
        return round(final_score, 3)

    def discover_evidence_chains(self, max_depth=4):
        """
        Dynamically finds all simple paths from Marketing Claims to target risk nodes
        (Patents or Licenses) without hardcoded traversal loops.
        """
        logger.info(f"Discovering dynamic evidence chains (Max Depth: {max_depth} hops)...")
        
        claims = [n for n, d in self.G.nodes(data=True) if d.get("label") == "Marketing_Claim"]
        risk_nodes = [n for n, d in self.G.nodes(data=True) if d.get("label") in ["Patent_Concept", "OpenSource_License"]]
        
        evidence_objects = []

        for claim in claims:
            for risk_node in risk_nodes:
                # Use NetworkX to find ALL simple paths between the claim and the risk
                # cutoff=max_depth prevents the search from taking forever on massive graphs
                try:
                    paths = list(itertools.islice(
                        nx.all_simple_paths(self.G, source=claim, target=risk_node, cutoff=max_depth),
                        50
                    ))

                    for path in paths:
                        confidence = self.calculate_path_confidence(path)
                        risk_type = self.G.nodes[risk_node].get("label")
                        
                        # Build the formal Evidence Object
                        evidence = {
                            "claim_id": claim,
                            "claim_text": self.G.nodes[claim].get("full_text", claim),
                            "risk_node": risk_node,
                            "risk_type": risk_type,
                            "path_length": len(path) - 1,
                            "confidence_score": confidence,
                            "reasoning_path": path
                        }
                        evidence_objects.append(evidence)
                        
                except (nx.NodeNotFound, nx.NetworkXError, nx.NetworkXNoPath):
                    continue

        # Sort by highest confidence first
        evidence_objects.sort(key=lambda x: x["confidence_score"], reverse=True)
        return evidence_objects

    def export_evidence(self):
        evidence_chains = self.discover_evidence_chains()
        output_path = self.data_dir / "processed" / "structured_evidence.json"
        output_path.write_text(json.dumps({"evidence_objects": evidence_chains}, indent=2), encoding="utf-8")
        logger.info(f"Exported {len(evidence_chains)} structured Evidence Objects to → {output_path}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    reasoner = DynamicPathReasoner(project_root / "data")
    reasoner.export_evidence()