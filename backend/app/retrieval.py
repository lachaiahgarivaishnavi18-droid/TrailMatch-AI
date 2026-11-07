import os
import re
import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from .nlp import normalize
from .schemas import Candidate, ProfileOutput, RetrievalOutput, TrialInput

_model = None


def retrieve(profile: ProfileOutput, trials: list[TrialInput], limit: int) -> RetrievalOutput:
    provider = os.getenv("EMBEDDING_PROVIDER", "local")
    vector_provider = os.getenv("VECTOR_PROVIDER", "numpy")
    if not trials:
        return RetrievalOutput(candidates=[], provider=provider)
    query = " ".join(profile.normalized_conditions + profile.normalized_medications)
    if not query:
        return RetrievalOutput(candidates=[], provider=provider)
    documents = [normalize(" ".join([t.title, *t.conditions, *t.interventions, t.summary])) for t in trials]
    tokenize = lambda s: re.findall(r"\w+", s.lower())
    bm25 = np.maximum(BM25Okapi([tokenize(x) for x in documents]).get_scores(tokenize(query)), 0)
    bm25 = bm25 / max(float(bm25.max()), 1e-9)
    if provider == "sentence_transformers":
        global _model
        from sentence_transformers import SentenceTransformer
        if _model is None:
            _model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
        vectors = _model.encode(documents, normalize_embeddings=True).astype("float32")
        q = _model.encode([query], normalize_embeddings=True).astype("float32")
        if vector_provider == "faiss":
            import faiss
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
            distances, ids = index.search(q, len(trials))
            similarity = np.zeros(len(trials))
            similarity[ids[0]] = distances[0]
        else:
            similarity = (vectors @ q.T).ravel()
        label = f"Sentence Transformers + BM25 ({vector_provider})"
    elif provider == "local":
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
        vectors = vectorizer.fit_transform(documents + [query])
        similarity = (vectors[:-1] @ vectors[-1].T).toarray().ravel()
        label = "Terminology-normalized TF-IDF + BM25 (offline baseline)"
    else:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")
    scores = .7 * np.clip(similarity, 0, 1) + .3 * bm25
    ordered = np.argsort(-scores)
    return RetrievalOutput(candidates=[Candidate(trial=trials[i], similarity=round(float(scores[i]), 4))
                                       for i in ordered[:limit] if scores[i] > .015], provider=label)
