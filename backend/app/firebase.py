import firebase_admin
from firebase_admin import firestore


def get_firebase_app():
    """Return the shared Firebase Admin app, initialising it when needed."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app()


def get_firestore_client():
    return firestore.client(app=get_firebase_app())
