"""Embedding-provider adapters.

Implementations sit behind the ``EmbeddingProvider`` protocol in
``app.adapters.protocols`` so the rest of the system never knows
which model is producing the vectors. Pick one via
``settings.embedding_provider``; see ``registry.get_embedding_provider``.
"""
