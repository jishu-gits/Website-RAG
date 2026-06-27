import sys
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("--- Calling /api/ingest ---")
# Using a dummy URL that won't take too long, or mocking ingestion
# Actually, if I just import the modules directly and check their vector_store instances:

from app.api.health import vector_store as vs_health
from app.api.ingest import vector_store as vs_ingest
from app.services.retrieval import vector_store as vs_retrieval
from app.services.vector_store import vector_store as vs_main

print(f"Health ID: {id(vs_health)}")
print(f"Ingest ID: {id(vs_ingest)}")
print(f"Retrieval ID: {id(vs_retrieval)}")
print(f"Main ID: {id(vs_main)}")

if id(vs_health) == id(vs_ingest):
    print("They match!")
else:
    print("Mismatch!")
