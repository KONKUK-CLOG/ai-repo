"""AWS Lambda ASGI entrypoint for the FastAPI app (LLM + tools).

Uses Mangum with lifespan disabled so the FastAPI lifespan hook is skipped
(stateless Lambda; no background workers in this build).
"""
from mangum import Mangum

from src.server.main import app

handler = Mangum(app, lifespan="off")
