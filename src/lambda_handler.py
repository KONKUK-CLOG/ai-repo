"""AWS Lambda ASGI entrypoint for the FastAPI app (e.g. LLM execute on demand).

Uses Mangum with lifespan disabled so FastAPI lifespan (scheduler, token manager)
does not run. For full EC2 behavior, use uvicorn and ENABLE_BACKGROUND_TASKS=true.

Set environment variable ENABLE_BACKGROUND_TASKS=false on Lambda if you mount the
same settings module elsewhere; with lifespan="off" the lifespan hook is skipped.
"""
from mangum import Mangum

from src.server.main import app

handler = Mangum(app, lifespan="off")
