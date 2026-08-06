"""
Vector Search Engine: Dense and TF-IDF semantic vector similarity search
for historical message retrieval and evidence matching.
Uses Python standard library with optional scikit-learn acceleration.
"""
import re
import math
from collections import Counter


def _tokenize(text):
    """Tokenize and normalize text into clean lower-case words."""
    if not text:
        return []
    return re.findall(r'\w+', text.lower())


class VectorSearchEngine:
    """TF-IDF vector search index over text documents."""

    def __init__(self):
        self.documents = []
        self.doc_ids = []
        self.vocabulary = {}
        self.idf = {}
        self.doc_vectors = []

    def fit_documents(self, doc_ids, text_list):
        """Build TF-IDF vector index from documents."""
        self.doc_ids = doc_ids
        self.documents = text_list
        doc_count = len(text_list)
        if doc_count == 0:
            return

        # 1. Build vocabulary and document frequency
        df = Counter()
        tokenized_docs = []
        for text in text_list:
            tokens = set(_tokenize(text))
            tokenized_docs.append(tokens)
            for t in tokens:
                df[t] += 1

        self.vocabulary = {term: idx for idx, term in enumerate(sorted(df.keys()))}

        # 2. Compute IDF
        for term, freq in df.items():
            self.idf[term] = math.log((doc_count + 1) / (freq + 1)) + 1.0

        # 3. Compute TF-IDF vectors for documents
        self.doc_vectors = []
        for text in text_list:
            vec = self._text_to_tfidf_vec(text)
            self.doc_vectors.append(vec)

    def _text_to_tfidf_vec(self, text):
        """Convert a text string to a sparse TF-IDF dictionary vector."""
        tokens = _tokenize(text)
        if not tokens:
            return {}

        tf = Counter(tokens)
        total_tokens = len(tokens)
        vec = {}
        for term, count in tf.items():
            if term in self.vocabulary:
                norm_tf = count / total_tokens
                vec[term] = norm_tf * self.idf.get(term, 1.0)
        return vec

    def _cosine_similarity(self, vec1, vec2):
        """Compute cosine similarity between two sparse term vectors."""
        if not vec1 or not vec2:
            return 0.0

        common_terms = set(vec1.keys()) & set(vec2.keys())
        if not common_terms:
            return 0.0

        dot_product = sum(vec1[t] * vec2[t] for t in common_terms)
        norm1 = math.sqrt(sum(v * v for v in vec1.values()))
        norm2 = math.sqrt(sum(v * v for v in vec2.values()))

        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def search(self, query_text, top_k=3, min_score=0.1):
        """Search top-k most similar documents by vector cosine similarity."""
        query_vec = self._text_to_tfidf_vec(query_text)
        if not query_vec:
            return []

        results = []
        for idx, doc_vec in enumerate(self.doc_vectors):
            score = self._cosine_similarity(query_vec, doc_vec)
            if score >= min_score:
                results.append((self.doc_ids[idx], score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
