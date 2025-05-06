# api/index.py
from app import app

# This is necessary for Vercel serverless deployment
handler = app
