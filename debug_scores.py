import sys
sys.path.insert(0, 'src')
from graph.knowledge_fusion import KnowledgeFusionPipeline, _DEP_ENRICHMENT
from graph.knowledge_fusion import _cosine_sim_np
from pathlib import Path

p = KnowledgeFusionPipeline(Path('data'), similarity_threshold=0.25)
p.load_pitch_claims()
p.load_dependencies()

claim_nodes = p._get_nodes_by_label('Marketing_Claim')
dep_nodes   = p._get_nodes_by_label('Software_Dependency', 'Code_Module')

claim_texts = [d.get('text', n) for n, d in claim_nodes]
dep_texts   = [
    f"{n} {_DEP_ENRICHMENT.get(n.lower().replace('-','_'), '')} {d.get('category', '')}".strip()
    for n, d in dep_nodes
]

claim_embs = p._encode_texts(claim_texts)
dep_embs   = p._encode_texts(dep_texts)

print('Claim:', claim_texts[0][:100])
print()

scores = [
    (dep_texts[i], float(_cosine_sim_np(claim_embs[0], dep_embs[i])))
    for i in range(len(dep_texts))
]
scores.sort(key=lambda x: -x[1])

print('Top 15 similarity scores:')
for text, score in scores[:15]:
    print(f'  {score:.4f}  {text}')

print()
print('Max score:', scores[0][1])
print('Scores above 0.25:', sum(1 for _, s in scores if s >= 0.25))
print('Scores above 0.20:', sum(1 for _, s in scores if s >= 0.20))
print('Scores above 0.15:', sum(1 for _, s in scores if s >= 0.15))