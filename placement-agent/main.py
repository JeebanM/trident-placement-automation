"""
main.py
───────
Application entrypoint.
Run with: uvicorn main:app --host 0.0.0.0 --port 8000
"""
from app.api.routes import create_app

app = create_app()
