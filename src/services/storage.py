"""
S3 storage service (Minio) for profile photos.

Upload photos from Telegram → Minio, return object key.
Download from Minio → bytes for sending via Telegram.
"""

import io
import logging
import uuid

from aiogram.types import BufferedInputFile
from miniopy_async import Minio

from src.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


def get_s3_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


async def ensure_bucket() -> None:
    """Create the photos bucket if it doesn't exist."""
    client = get_s3_client()
    exists = await client.bucket_exists(settings.minio_bucket)
    if not exists:
        await client.make_bucket(settings.minio_bucket)
        import json

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{settings.minio_bucket}/*"],
                }
            ],
        }
        await client.set_bucket_policy(settings.minio_bucket, json.dumps(policy))
        logger.info(
            "Created bucket '%s' with public read policy", settings.minio_bucket
        )


async def upload_photo(data: bytes, content_type: str = "image/jpeg") -> str:
    """Upload photo bytes to S3. Returns the object key (path)."""
    client = get_s3_client()
    key = f"photos/{uuid.uuid4().hex}.jpg"

    await client.put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )

    logger.info("Uploaded photo: %s (%d bytes)", key, len(data))
    return key


async def download_photo(key: str) -> bytes:
    """Download photo from S3 by key."""
    client = get_s3_client()
    response = await client.get_object(settings.minio_bucket, key)
    data = await response.read()
    response.close()
    await response.release()
    return data


def is_s3_key(storage_path: str) -> bool:
    """Check if storage_path is an S3 key (vs a Telegram file_id)."""
    return storage_path.startswith("photos/")


async def resolve_photo(storage_path: str) -> str | BufferedInputFile:
    """Return a value usable with answer_photo.

    - S3 keys → download from Minio and return as BufferedInputFile
      (Telegram can't reach localhost Minio).
    - Telegram file_ids → return as-is.
    """
    if is_s3_key(storage_path):
        try:
            data = await download_photo(storage_path)
            return BufferedInputFile(data, filename="photo.jpg")
        except Exception:
            logger.warning("Failed to download %s from S3", storage_path)
            return storage_path
    return storage_path
