"""
wsgi.py — Production entry point for gunicorn.

gunicorn imports this file and calls the `app` object.
We also ensure the database is initialised here so
`setup_database()` runs on every cold start / dyno spin-up.

Start command on Render:
    gunicorn wsgi:app
"""

from app import app, setup_database

setup_database()
