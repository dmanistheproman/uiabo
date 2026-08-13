# Shared pipeline code

This folder contains code used by more than one pipeline component.

Use it for:

- Shared Pydantic interfaces
- Allowed enum values
- Common component errors
- Version information

Do not place one member's private implementation logic here. Changes to shared interfaces require agreement from every affected member.

The active API models currently remain in `app/schemas.py`. Shared pipeline models can be moved here later as part of an agreed integration change.

