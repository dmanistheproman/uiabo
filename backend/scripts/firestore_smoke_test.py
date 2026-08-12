from app.firebase import get_firestore_client


def main():
    db = get_firestore_client()

    document_ref = (
        db.collection("system_tests")
        .document("backend_connection")
    )

    document_ref.set(
        {
            "status": "ok",
            "source": "FastAPI backend"
        }
    )

    document = document_ref.get()

    if document.exists:
        print("Firestore connection successful!")
        print(document.to_dict())
    else:
        print("Document was not found.")


if __name__ == "__main__":
    main()