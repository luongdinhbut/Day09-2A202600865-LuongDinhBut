from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from rag.parser import parse_policy_markdown

class ChromaPolicyStore:
    """Student scaffold for the real Chroma-backed policy index."""

    def __init__(
        self,
        persist_directory: Path,
        embedding_model: Any,
        collection_name: str = "policy_chunks",
    ) -> None:
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedding_model = embedding_model

    def ensure_index(self, markdown_path: Path) -> None:
        if self.collection.count() == 0:
            self.rebuild(markdown_path)

    def rebuild(self, markdown_path: Path) -> None:
        with open(markdown_path, 'r', encoding='utf-8') as f:
            text = f.read()
            
        chunks = parse_policy_markdown(text)
        if not chunks:
            return
            
        texts = [chunk["rendered_text"] for chunk in chunks]
        embeddings = self.embedding_model.embed_documents(texts)
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "citation": chunk["citation"],
                "section_h2": chunk["section_h2"],
                "section_h3": chunk["section_h3"]
            }
            for chunk in chunks
        ]
        
        existing = self.collection.get()
        if existing and existing["ids"]:
            self.collection.delete(ids=existing["ids"])
            
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas
        )

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        query_embedding = self.embedding_model.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        hits = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0] if "distances" in results and results["distances"] else [0.0] * len(docs)
            
            for doc, meta, dist in zip(docs, metas, dists):
                hits.append({
                    "citation": meta.get("citation", ""),
                    "content": doc,
                    "distance": dist
                })
        return hits
