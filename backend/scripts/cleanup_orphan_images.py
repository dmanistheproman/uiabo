"""Review old unreferenced image uploads; --apply deletes only confirmed orphans.

Run with the same environment as the backend. Dry-run is the default. A database
read failure aborts cleanup; unknown commit outcomes are never assumed absent.
"""
import argparse
from datetime import datetime, timedelta, timezone
import re
from app.analyses.images import get_image_storage
from app.firebase import get_firestore_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    images, client = get_image_storage(), get_firestore_client()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    pattern = re.compile(r'^analysis-images/[a-f0-9]{64}/([a-f0-9]{32})/[a-f0-9-]{36}$')
    count = 0
    for blob in images.bucket.list_blobs(prefix='analysis-images/', timeout=30):
        match = pattern.fullmatch(blob.name)
        if not match or not blob.updated or blob.updated > cutoff:
            continue
        result = client.collection('analysis_results').document(match[1]).get().to_dict() or {}
        saved = result.get('saved_image') or {}
        if saved.get('object_path') == blob.name and int(saved.get('generation', 0)) == int(blob.generation):
            continue
        count += 1
        print(('Removing' if args.apply else 'Would remove'), blob.name)
        if args.apply:
            blob.delete(if_generation_match=blob.generation, timeout=30)
    print(f'{count} confirmed orphan image(s); apply={args.apply}')


if __name__ == '__main__':
    main()
