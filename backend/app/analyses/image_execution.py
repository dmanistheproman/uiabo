"""Bound expensive image work without releasing a slot while a worker still runs."""
import asyncio
from threading import BoundedSemaphore
from fastapi import HTTPException

_slot = BoundedSemaphore(1)


async def run_image_work(function, *, timeout=180):
    if not _slot.acquire(blocking=False):
        raise HTTPException(429, detail={"error_code": "IMAGE_ANALYSIS_BUSY",
            "message": "Another image is being checked. Please try again shortly."})

    def work():
        try:
            return function()
        finally:
            _slot.release()

    # Cancellation/timeout stops waiting, not the underlying native inference.
    # The worker holds its slot until it actually exits and never writes results.
    task = asyncio.create_task(asyncio.to_thread(work))
    task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout)
    except TimeoutError:
        raise HTTPException(504, detail={"error_code": "IMAGE_ANALYSIS_TIMEOUT",
            "message": "The image check took too long. Please try again shortly."}) from None
