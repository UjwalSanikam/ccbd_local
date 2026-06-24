import json
import logging
from pathlib import Path
import networkx as nx
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class SemanticFusionPipeline:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.G = nx.DiGraph()
        
        # Load the lightweight, high-performance embedding model
        logger.info("Loading SentenceTransformer model (all-MiniLM-L6-v2)...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def load_nodes(self):
        logger.info("Initializing Data Ingestion...")

        # 1. Load Codebase
        code_path = self.data_dir / "processed" / "codebase_knowledge.json"
        if code_path.exists():
            code_data = json.loads(code_path.read_text(encoding="utf-8"))
            if "import_graph_structure" in code_data:
                for node in code_data["import_graph_structure"].get("nodes", []):
                    self.G.add_node(node["id"], label="Code_Module", type=node.get("type"))
                for edge in code_data["import_graph_structure"].get("edges", []):
                    self.G.add_edge(edge["source"], edge["target"], relationship="IMPORTS")

        # 2. Load Patents
        patent_path = self.data_dir / "processed" / "knowledge_base.json"
        if patent_path.exists():
            patent_data = json.loads(patent_path.read_text(encoding="utf-8"))
            for triple in patent_data.get("triples", []):
                self.G.add_node(triple["head"], label="Patent_Concept")
                self.G.add_node(triple["tail"], label="Patent_Concept")
                self.G.add_edge(triple["head"], triple["tail"], relationship=triple["relationship"])

        # 3. Load Pitch Deck
        parsed_files = list((self.data_dir / "processed").glob("*_parsed.json"))
        claims_path = parsed_files[0] if parsed_files else None

        if claims_path and claims_path.exists():
            logger.info("Fusing Track 1: Startup Marketing Assertions...")
            claims_data = json.loads(claims_path.read_text(encoding="utf-8"))
            startup_name = claims_path.stem.replace("_parsed", "").replace("_", " ").title()
            company_node = f"{startup_name} (Pitch Deck)"
            
            claims_list = claims_data.get("claims", claims_data.get("technical_claims", []))
            for idx, claim in enumerate(claims_list):
                text = claim.get('sentence', str(claim))
                claim_id = f"Claim_{idx}: {text[:30]}..."
                self.G.add_node(claim_id, label="Marketing_Claim", full_text=text)
                self.G.add_edge(company_node, claim_id, relationship="ASSERTS")

        # 4. Load Track 4: Open-Source License Intelligence
        license_path = self.data_dir / "processed" / "license_knowledge.json"
        if license_path.exists():
            logger.info("Fusing Track 4: Open-Source Compliance Data...")
            license_data = json.loads(license_path.read_text(encoding="utf-8"))
            for entry in license_data.get("licenses", []):
                self.G.add_node(entry["license"], label="OpenSource_License")
                self.G.add_edge(entry["module"], entry["license"], relationship=entry["relationship"])

    def _get_normalized_embeddings(self, texts):
        """Generates vectors and normalizes them for Cosine Similarity search in FAISS."""
        embeddings = self.model.encode(texts)
        faiss.normalize_L2(embeddings)
        return embeddings

    def execute_faiss_semantic_bridging(self):
        logger.info("Executing FAISS Vector Similarity Bridging...")

        patent_nodes = [n for n, d in self.G.nodes(data=True) if d.get('label') == 'Patent_Concept']
        code_nodes = [n for n, d in self.G.nodes(data=True) if d.get('label') == 'Code_Module']
        claim_nodes = [n for n, d in self.G.nodes(data=True) if d.get('label') == 'Marketing_Claim']

        if not (patent_nodes and code_nodes and claim_nodes):
            logger.warning("Missing one of the data tracks. Skipping semantic bridging.")
            return

        # ==========================================
        # BRIDGE 1: Code Modules <--> Patent Concepts
        # ==========================================
        logger.info("Building FAISS Index for Patent Concepts...")
        patent_embeddings = self._get_normalized_embeddings(patent_nodes)
        dim = patent_embeddings.shape[1]
        
        # IndexFlatIP uses Inner Product. Since vectors are normalized, IP == Cosine Similarity
        patent_index = faiss.IndexFlatIP(dim)
        patent_index.add(patent_embeddings)

        # Clean code paths so the NLP model understands them (e.g., "src.crypto_auth" -> "src crypto auth")
        clean_code_texts = [n.replace('.', ' ').replace('_', ' ') for n in code_nodes]
        code_embeddings = self._get_normalized_embeddings(clean_code_texts)

        # Search for top 2 closest patent concepts for every code module
        k = 2 
        distances, indices = patent_index.search(code_embeddings, k)

        # Link them if the mathematical similarity is strong enough
        overlap_threshold = 0.40 
        for i, code_node in enumerate(code_nodes):
            for j in range(k):
                score = distances[i][j]
                if score >= overlap_threshold:
                    patent_node = patent_nodes[indices[i][j]]
                    self.G.add_edge(code_node, patent_node, relationship="REQUIRES_IP_REVIEW", similarity=float(score))
                    logger.info(f"🔗 Vector Match [Score: {score:.2f}]: '{code_node}' -> '{patent_node}'")

        # ==========================================
        # BRIDGE 2: Marketing Claims <--> Code Modules
        # ==========================================
        logger.info("Building FAISS Index for Codebase Modules...")
        code_index = faiss.IndexFlatIP(dim)
        code_index.add(code_embeddings)

        claim_texts = [self.G.nodes[n].get('full_text', n) for n in claim_nodes]
        claim_embeddings = self._get_normalized_embeddings(claim_texts)

        distances, indices = code_index.search(claim_embeddings, k)

        for i, claim_node in enumerate(claim_nodes):
            for j in range(k):
                score = distances[i][j]
                if score >= overlap_threshold:
                    code_node = code_nodes[indices[i][j]]
                    self.G.add_edge(claim_node, code_node, relationship="POTENTIALLY_IMPLEMENTED_BY", similarity=float(score))
                    logger.info(f"🔗 Vector Match [Score: {score:.2f}]: Claim -> '{code_node}'")

    def export_fused_graph(self):
        output_path = self.data_dir / "processed" / "fused_knowledge_graph.json"
        serializable_graph = {
            "nodes": [{"id": n, **d} for n, d in self.G.nodes(data=True)],
            "links": [{"source": u, "target": v, **d} for u, v, d in self.G.edges(data=True)]
        }
        output_path.write_text(json.dumps(serializable_graph, indent=2), encoding="utf-8")
        logger.info(f"Semantic Graph saved to → {output_path}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    pipeline = SemanticFusionPipeline(project_root / "data")
    pipeline.load_nodes()
    pipeline.execute_faiss_semantic_bridging()
    pipeline.export_fused_graph()