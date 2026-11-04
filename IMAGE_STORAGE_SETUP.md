# Save analysis images

Scope: completed deepfake and image-context checks. OCR images are not retained.

## Firebase setup

1. Open the UIABO Firebase project, then **Storage**.
2. Enable the Blaze billing plan if required and create a private bucket. Choose a location deliberately; regional pricing and free-tier eligibility differ.
3. Use restrictive Storage rules. The app accesses images through its authenticated backend, so direct mobile/browser Storage access is unnecessary. Do not enable public access or test-mode rules.
4. Give the existing backend service account permission to create, read and delete objects in this bucket (for example, bucket-scoped `roles/storage.objectUser`). Do not grant public access.
5. Add these to the project root `.env` after the bucket is ready:

```dotenv
SAVE_ANALYSIS_IMAGES=1
FIREBASE_STORAGE_BUCKET=your-actual-bucket-name.firebasestorage.app
```

Use the bucket name without `gs://`. Restart the backend with `--env-file ..\.env` and restart Expo. No new image-storage API key is needed. With `SAVE_ANALYSIS_IMAGES` unset or `0`, image checks retain the previous results-only behaviour.

Example restrictive Firebase Storage rules for a backend-only bucket:

```
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /{allPaths=**} {
      allow read, write: if false;
    }
  }
}
```

These rules do not restrict the Admin SDK; backend IAM permissions and endpoint ownership checks protect its access. Review existing bucket uses before replacing rules.

## What changes

- Original uploaded bytes are saved after analysis succeeds. No recompression changes the image that was checked; embedded metadata is retained too.
- Maximum upload: 10 MiB and 25 megapixels; JPEG/PNG only.
- Firestore stores the object path, generation, media type and byte size with the result.
- Images are available only through owner-authenticated GET `/analysis/results/{result_id}/image`.
- **Remove saved image** calls DELETE on that endpoint; the assessment remains in history.
- Old results have no stored image and cannot be backfilled from filenames.
- No public download tokens or signed URLs are generated.
- No portal image access is granted in this change.

## Charging and partial failures

The image must upload before a completed result is saved and allowance is charged. If uploading fails, no completed result is saved and the same request key can be retried. If result saving fails, the backend checks whether the transaction committed before cleaning up the object. An uncertain outcome preserves the object to avoid breaking a result that may have been saved.

Cloud Storage and Firestore do not share a transaction. An interrupted upload/unknown database outcome can leave an orphan. The maintenance command `python -m scripts.cleanup_orphan_images` lists uploads over one hour old with no matching saved reference; add `--apply` to remove confirmed orphans. Database read failures stop cleanup. Do not apply an age-based bucket lifecycle rule without also deciding how saved history should expire.

Images remain until the user removes them. Cloud bucket soft-delete/versioning settings may retain recoverable copies and incur charges after removal; review these settings in the console. Account deletion now removes owned image objects through the resumable cleanup described in [backend fixes](RELIABILITY_UPDATES.md).

Image-context provider failures no longer consume allowance. See [backend fixes](RELIABILITY_UPDATES.md).

## Verify before sharing

- Submit one new deepfake check and one image-context check.
- Reopen each result after restarting the app; check the original image appears.
- Confirm the object exists in Storage and its reference exists in `analysis_results`.
- Try the result/image endpoint using another test account; it must be denied.
- Remove an image, reopen the result, and confirm the assessment stays but the image is unavailable.
- Check billing usage. Budget alerts notify you; they do not cap charges.

Local mocked tests cover save/retry/read/delete, ownership, suspension, upload/commit failures and validation. Live bucket upload/read/delete has been verified. Authenticated emulator verification is still required.

References: [Admin Storage setup](https://firebase.google.com/docs/storage/admin/start), [billing requirements](https://firebase.google.com/docs/storage/faqs-storage-changes-announced-sept-2024), [Storage pricing](https://cloud.google.com/storage/pricing).

Verification on 1 November 2026: 1,124 backend tests passed (four live-provider cases excluded), including 16 image-storage tests. Android export passed. A 112-byte generated sample was uploaded to the configured bucket, read byte-for-byte, checked for anonymous-access denial (403), and removed. Firestore persistence was simulated in memory; real records and allowances were not changed.


## Desktop activation

The local root `.env` now enables saving to `uiabo-69497.firebasestorage.app`. The bucket is in `US-EAST1`, has no public IAM bindings, and Firebase Storage rules deny direct client reads/writes. The existing backend service account successfully uploaded, read and removed the test object. Restart the backend and Expo to use the new feature.

The bucket currently has a seven-day soft-delete policy: removed objects are unavailable normally but may remain recoverable and billable for seven days. That policy was not changed.
