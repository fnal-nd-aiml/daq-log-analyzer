"""
File: chroma_store.py
Purpose: ChromaDB storage for semantic search.
Category: Utility
Author: artdaq team
Depends: models
Exports: ChromaStore
Complexity: Medium | Lines: 200
"""

import logging
from pathlib import Path
from typing import Any, Awaitable, Callable
from srcs.models import SimilarInvestigation
logger = logging.getLogger(__name__)
EmbedFn = Callable[[str], Awaitable[list[float]]]

class ChromaStore:
    COLLECTIONS = {'investigations': 'Past investigation embeddings for similarity search', 'error_explanations': 'Error pattern explanation embeddings', 'function_summaries': 'Code function summary embeddings for understanding search', 'causal_mechanisms': 'Reusable causal chain template embeddings'}

    def __init__(self, persist_path: str | Path, embed_fn: EmbedFn):
        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.embed_fn = embed_fn
        self._client: Any = None
        self._collections: dict = {}

    @property
    def client(self) -> Any:
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.persist_path))
            self._init_collections()
        return self._client

    def _init_collections(self) -> None:
        for name, desc in self.COLLECTIONS.items():
            self._collections[name] = self._client.get_or_create_collection(name=name, metadata={'description': desc})

    def _get_collection(self, name: str) -> Any:
        _ = self.client
        return self._collections[name]

    async def store_investigation_embedding(self, investigation_id: str, description: str, metadata: dict) -> None:
        collection = self._get_collection('investigations')
        embedding = await self.embed_fn(description)
        clean_metadata = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                clean_metadata[k] = v
            else:
                clean_metadata[k] = str(v)
        try:
            collection.add(ids=[investigation_id], embeddings=[embedding], documents=[description], metadatas=[clean_metadata] if clean_metadata else None)
        except Exception as e:
            if 'already exists' in str(e).lower():
                collection.update(ids=[investigation_id], embeddings=[embedding], documents=[description], metadatas=[clean_metadata] if clean_metadata else None)
            else:
                logger.error(f'Failed to store investigation embedding: {e}')
                raise

    async def find_similar_investigations(self, description: str, n: int=5) -> list[SimilarInvestigation]:
        collection = self._get_collection('investigations')
        if collection.count() == 0:
            return []
        embedding = await self.embed_fn(description)
        results = collection.query(query_embeddings=[embedding], n_results=min(n, collection.count()))
        return self._parse_results(results)

    def _parse_results(self, results: dict) -> list[SimilarInvestigation]:
        similar: list[SimilarInvestigation] = []
        if not results.get('ids') or not results['ids'][0]:
            return similar
        ids = results['ids'][0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]
        for i, inv_id in enumerate(ids):
            metadata = metadatas[i] if i < len(metadatas) else {}
            distance = distances[i] if i < len(distances) else 1.0
            similarity = 1.0 / (1.0 + distance)
            similar.append(SimilarInvestigation(investigation_id=inv_id, similarity_score=similarity, root_cause=metadata.get('root_cause'), was_correct=metadata.get('was_correct'), outcome=metadata.get('outcome')))
        return similar

    async def store_error_explanation(self, pattern_id: str, explanation: str, metadata: dict) -> None:
        collection = self._get_collection('error_explanations')
        embedding = await self.embed_fn(explanation)
        clean_metadata = {k: v for k, v in metadata.items() if v is not None}
        try:
            collection.add(ids=[pattern_id], embeddings=[embedding], documents=[explanation], metadatas=[clean_metadata] if clean_metadata else None)
        except Exception as e:
            if 'already exists' in str(e).lower():
                collection.update(ids=[pattern_id], embeddings=[embedding], documents=[explanation], metadatas=[clean_metadata] if clean_metadata else None)
            else:
                raise

    async def find_similar_errors(self, error_description: str, n: int=5) -> list[dict]:
        collection = self._get_collection('error_explanations')
        if collection.count() == 0:
            return []
        embedding = await self.embed_fn(error_description)
        results = collection.query(query_embeddings=[embedding], n_results=min(n, collection.count()))
        similar = []
        if results.get('ids') and results['ids'][0]:
            for i, pattern_id in enumerate(results['ids'][0]):
                metadata = results.get('metadatas', [[]])[0]
                meta = metadata[i] if i < len(metadata) else {}
                distance = results.get('distances', [[]])[0][i] if results.get('distances') else 1.0
                similarity = 1.0 / (1.0 + distance)
                similar.append({'pattern_id': pattern_id, 'similarity': similarity, **meta})
        return similar

    async def store_function_summary(self, function_id: str, summary: str, metadata: dict) -> None:
        collection = self._get_collection('function_summaries')
        embedding = await self.embed_fn(summary)
        clean_metadata = {k: v for k, v in metadata.items() if v is not None}
        for k, v in clean_metadata.items():
            if not isinstance(v, (str, int, float, bool)):
                clean_metadata[k] = str(v)
        try:
            collection.add(ids=[function_id], embeddings=[embedding], documents=[summary], metadatas=[clean_metadata] if clean_metadata else None)
        except Exception as e:
            if 'already exists' in str(e).lower():
                collection.update(ids=[function_id], embeddings=[embedding], documents=[summary], metadatas=[clean_metadata] if clean_metadata else None)
            else:
                raise

    async def find_similar_functions(self, description: str, n: int=10, file_filter: str | None=None) -> list[dict]:
        collection = self._get_collection('function_summaries')
        if collection.count() == 0:
            return []
        embedding = await self.embed_fn(description)
        where_filter = None
        if file_filter:
            where_filter = {'file_path': {'$contains': file_filter}}
        results = collection.query(query_embeddings=[embedding], n_results=min(n, collection.count()), where=where_filter)
        similar = []
        if results.get('ids') and results['ids'][0]:
            for i, func_id in enumerate(results['ids'][0]):
                metadata = results.get('metadatas', [[]])[0]
                meta = metadata[i] if i < len(metadata) else {}
                documents = results.get('documents', [[]])[0]
                summary = documents[i] if i < len(documents) else ''
                distance = results.get('distances', [[]])[0][i] if results.get('distances') else 1.0
                similarity = 1.0 / (1.0 + distance)
                similar.append({'function_id': func_id, 'summary': summary, 'similarity': similarity, **meta})
        return similar

    async def store_causal_mechanism(self, mechanism_id: str, description: str, metadata: dict) -> None:
        collection = self._get_collection('causal_mechanisms')
        embedding = await self.embed_fn(description)
        clean_metadata = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                clean_metadata[k] = v
            elif isinstance(v, list):
                clean_metadata[k] = ','.join((str(x) for x in v))
            else:
                clean_metadata[k] = str(v)
        try:
            collection.add(ids=[mechanism_id], embeddings=[embedding], documents=[description], metadatas=[clean_metadata] if clean_metadata else None)
        except Exception as e:
            if 'already exists' in str(e).lower():
                collection.update(ids=[mechanism_id], embeddings=[embedding], documents=[description], metadatas=[clean_metadata] if clean_metadata else None)
            else:
                raise

    async def find_similar_mechanisms(self, situation_description: str, n: int=5, category: str | None=None) -> list[dict]:
        collection = self._get_collection('causal_mechanisms')
        if collection.count() == 0:
            return []
        embedding = await self.embed_fn(situation_description)
        where_filter = None
        if category:
            where_filter = {'category': category}
        results = collection.query(query_embeddings=[embedding], n_results=min(n, collection.count()), where=where_filter)
        similar = []
        if results.get('ids') and results['ids'][0]:
            for i, mech_id in enumerate(results['ids'][0]):
                metadata = results.get('metadatas', [[]])[0]
                meta = metadata[i] if i < len(metadata) else {}
                documents = results.get('documents', [[]])[0]
                description = documents[i] if i < len(documents) else ''
                distance = results.get('distances', [[]])[0][i] if results.get('distances') else 1.0
                similarity = 1.0 / (1.0 + distance)
                components = meta.get('components', '')
                if isinstance(components, str) and components:
                    components = components.split(',')
                similar.append({'mechanism_id': mech_id, 'description': description, 'similarity': similarity, 'category': meta.get('category'), 'components': components, 'typical_evidence': meta.get('typical_evidence')})
        return similar

    async def extract_and_store_mechanism(self, chain_id: str, root_cause: str, final_effect: str, steps: list[dict], category: str | None=None) -> str:
        from srcs.models import generate_id
        mechanism_parts = [f'Root cause: {root_cause}']
        for i, step in enumerate(steps):
            mechanism_parts.append(f"Step {i + 1}: {step.get('cause', 'Unknown')} -> {step.get('effect', 'Unknown')}")
        mechanism_parts.append(f'Final effect: {final_effect}')
        description = '\n'.join(mechanism_parts)
        mechanism_id = generate_id()
        import re
        components = set()
        full_text = f'{root_cause} {final_effect} ' + ' '.join((f"{s.get('cause', '')} {s.get('effect', '')}" for s in steps))
        for match in re.findall('\\b([A-Z][a-zA-Z]+(?:Manager|Handler|Service|Controller|Module)?)\\b', full_text):
            components.add(match)
        metadata = {'source_chain_id': chain_id, 'category': category or 'general', 'components': list(components)[:10], 'step_count': len(steps)}
        await self.store_causal_mechanism(mechanism_id, description, metadata)
        return mechanism_id