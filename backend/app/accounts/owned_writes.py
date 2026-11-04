"""Prevent late feedback/report writes from recreating deleted personal data."""
from fastapi import HTTPException
from google.cloud import firestore
from app.accounts.roles import require_account_type


def write_owned(client, collection, key, owner, value, *, require_existing=False):
    reference = client.collection(collection).document(key)

    @firestore.transactional
    def write(tx):
        profile = client.collection("users").document(owner).get(transaction=tx).to_dict()
        previous = reference.get(transaction=tx).to_dict()
        require_account_type(profile, "app")
        if not profile or profile.get("account_status") != "active":
            raise HTTPException(403, detail={"error_code": "ACCOUNT_UNAVAILABLE", "message": "This account is currently unavailable."})
        if require_existing and not previous:
            raise HTTPException(404, detail={"error_code": "RECORD_NOT_FOUND", "message": "This record is no longer available."})
        if previous and previous.get("user_id") != owner:
            raise HTTPException(409, detail={"error_code": "RECORD_CONFLICT", "message": "This record could not be updated."})
        tx.set(reference, value)
    write(client.transaction())
