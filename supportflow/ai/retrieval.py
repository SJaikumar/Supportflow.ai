"""Auditable knowledge search: pure-Python BM25 plus optional OpenAI/FAISS dense index.

The local BM25 preview works without an API key. In API mode, both rankings are
combined with reciprocal rank fusion; citations always reference local files.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from math import log
from pathlib import Path
import json
import re
import threading

# Keep this module import-safe before the test fixture selects its database path.
ROOT = Path(__file__).resolve().parents[2]

DOC_DIR = ROOT / 'knowledge_base'
INDEX_DIR = ROOT / 'data' / 'ai_index'
STOP = set('a an and are as at be but by can do does for from has have how i if in is it me my of on or our please should so that the their them there these this to was we what when where which who will with you your after before about'.split())
WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)


def tokens(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if len(w)>1 and w not in STOP]


@dataclass(frozen=True)
class Passage:
    citation: str
    filename: str
    text: str
    chunk: int

    def as_dict(self, score: float | None = None) -> dict:
        result = {'citation': self.citation, 'filename': self.filename, 'passage': self.text}
        if score is not None: result['score'] = round(float(score), 4)
        return result


def load_passages(directory: Path = DOC_DIR) -> list[Passage]:
    passages: list[Passage] = []
    for path in sorted(directory.glob('*.md')):
        if path.is_symlink(): continue
        content = path.read_text(encoding='utf-8')
        # Each paragraph has a stable source identifier; cap long paragraphs.
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if len(tokens(p)) >= 5]
        for i, para in enumerate(paragraphs, 1):
            passages.append(Passage(f'{path.name}#p{i}', path.name, para[:1600], i))
    return passages


class BM25:
    """Small, deterministic Okapi BM25 index (k1=1.5, b=.75)."""
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self.docs = [Counter(tokens(p.text)) for p in passages]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.avgdl = sum(self.lengths) / len(self.lengths) if self.lengths else 0
        self.df = Counter(t for c in self.docs for t in c)

    def search(self, text: str, limit: int = 8) -> list[tuple[int, float]]:
        n = len(self.docs)
        if not n: return []
        scores = []
        for i, counts in enumerate(self.docs):
            score = 0.0
            for term in set(tokens(text)):
                f = counts[term]
                if f == 0: continue
                idf = log(1+(n-self.df[term]+0.5)/(self.df[term]+0.5))
                denom = f + 1.5 * (1-.75+.75*self.lengths[i]/max(self.avgdl,1))
                score += idf * (f*2.5) / denom
            if score > 0:
                scores.append((i, score))
        return sorted(scores, key=lambda p:(-p[1], p[0]))[:limit]


def reciprocal_rank_fusion(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    scores = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, 1):
            scores[idx] = scores.get(idx,0.0) + 1.0 / (k+rank)
    return sorted(scores.items(),key=lambda item:(-item[1],item[0]))


class DenseUnavailable(RuntimeError):
    pass


class FaissEmbeddings:
    """Persist a FAISS cosine-similarity index keyed by document hash and model.

    No embedding vectors, credentials or customer details are committed to Git.
    """
    _lock = threading.Lock()

    def __init__(self, *, api_key: str, model: str = 'text-embedding-3-small', cache_dir: Path = INDEX_DIR):
        self.api_key, self.model, self.cache_dir = api_key, model, cache_dir

    def _vectors(self, texts: list[str]):
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, timeout=25, max_retries=1)
        result = client.embeddings.create(model=self.model, input=texts)
        return [entry.embedding for entry in sorted(result.data,key=lambda x:x.index)]

    def search(self, passages: list[Passage], query: str, limit: int = 8) -> list[tuple[int,float]]:
        if not passages: return []
        try:
            import faiss
            import numpy as np
        except ImportError as exc:
            raise DenseUnavailable('faiss-cpu/numpy not installed') from exc
        digest = sha256(json.dumps([(p.citation,p.text) for p in passages],ensure_ascii=False).encode()).hexdigest()
        self.cache_dir.mkdir(parents=True,exist_ok=True)
        meta_path = self.cache_dir/'meta.json'
        index_path = self.cache_dir/'passages.faiss'
        with self._lock:
            metadata = {}
            if meta_path.exists() and index_path.exists():
                try: metadata=json.loads(meta_path.read_text(encoding='utf-8'))
                except (OSError,ValueError): pass
            if metadata.get('fingerprint') == digest and metadata.get('model') == self.model:
                try: index=faiss.read_index(str(index_path))
                except Exception: index=None
            else: index=None
            if index is None or index.ntotal != len(passages):
                embeddings=np.asarray(self._vectors([p.text for p in passages]),dtype='float32')
                if embeddings.ndim!=2 or embeddings.shape[0]!=len(passages):
                    raise DenseUnavailable('Embedding service returned invalid vectors')
                faiss.normalize_L2(embeddings)
                index=faiss.IndexFlatIP(embeddings.shape[1])
                index.add(embeddings)
                temp_path=self.cache_dir/'passages.tmp.faiss'
                faiss.write_index(index,str(temp_path))
                temp_path.replace(index_path)
                temp_meta=self.cache_dir/'meta.tmp.json'
                temp_meta.write_text(json.dumps({'fingerprint':digest,'model':self.model,'count':len(passages)}),encoding='utf-8')
                temp_meta.replace(meta_path)
        q=np.asarray(self._vectors([query]),dtype='float32')
        faiss.normalize_L2(q)
        distances,indices=index.search(q,min(limit,len(passages)))
        return [(int(i),float(s)) for i,s in zip(indices[0],distances[0]) if i>=0 and s>=0.42]


class KnowledgeSearch:
    def __init__(self, directory: Path = DOC_DIR, dense: FaissEmbeddings | None = None):
        self.passages=load_passages(directory)
        self.bm25=BM25(self.passages)
        self.dense=dense

    def search(self, query: str, limit: int = 5) -> dict:
        lexical=self.bm25.search(query,limit=10)
        dense_matches=[]
        mode='BM25 only'
        warning=None
        if self.dense:
            try:
                dense_matches=self.dense.search(self.passages,query,limit=10)
                mode='Hybrid FAISS + BM25'
            except Exception as exc:
                # Fail safe: no false claim that a semantic search succeeded.
                mode='BM25 only'
                warning=f'Dense search unavailable ({type(exc).__name__}); using BM25 only.'
        rankings=[[idx for idx,_ in lexical]]
        if dense_matches:rankings.append([idx for idx,_ in dense_matches])
        # If FAISS is enabled but does not retrieve anything above confidence threshold,
        # the verified BM25 ranking still provides appropriate policy evidence.
        ordered=reciprocal_rank_fusion(rankings)
        lookup=dict(lexical)
        results=[]
        for i,score in ordered[:limit]:
            p=self.passages[i]
            results.append({**p.as_dict(score), 'bm25_score':round(lookup.get(i,0),4)})
        return {'mode': mode,'query':query,'passages':results,'warning':warning}
