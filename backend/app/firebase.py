import firebase_admin
from firebase_admin import firestore
from dotenv import load_dotenv
from pathlib import Path


def get_firebase_app():
    """Return the shared Firebase Admin app, initialising it when needed."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        return firebase_admin.initialize_app()


def get_firestore_client():
    return firestore.client(app=get_firebase_app())
