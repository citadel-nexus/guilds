# src/services/__init__.py
"""
Sentinel memory-loop service layer.

Thin async wrappers over embedding, FAISS, Notion, Supabase,
Bedrock, NATS, and ElevenLabs used by the webhook handlers and
the FAISS indexing worker.
"""
