import os
import logging
from typing import Optional

from ..config import settings
import os as _os

# Configure logging
logger = logging.getLogger(__name__)


class StorageService:
    @staticmethod
    def _resolved_s3_config():
        # Direct environment variable reading with multiple fallbacks
        bucket = _os.getenv("APP_S3_BUCKET") or _os.getenv(
            "S3_BUCKET") or settings.s3_bucket
        region = _os.getenv("APP_S3_REGION") or _os.getenv(
            "S3_REGION") or settings.s3_region
        endpoint = _os.getenv("APP_S3_ENDPOINT_URL") or _os.getenv(
            "S3_ENDPOINT_URL") or settings.s3_endpoint_url
        public_base = _os.getenv("APP_S3_PUBLIC_BASE_URL") or _os.getenv(
            "S3_PUBLIC_BASE_URL") or settings.s3_public_base_url
        use_path_style_env = _os.getenv(
            "APP_S3_USE_PATH_STYLE") or _os.getenv("S3_USE_PATH_STYLE")

        # Debug logging to understand what's happening
        logger.info(
            f"S3 Config Debug - settings.s3_bucket: {settings.s3_bucket}")
        logger.info(
            f"S3 Config Debug - settings.storage_backend: {settings.storage_backend}")
        logger.info(
            f"S3 Config Debug - APP_S3_BUCKET env: {_os.getenv('APP_S3_BUCKET')}")
        logger.info(
            f"S3 Config Debug - S3_BUCKET env: {_os.getenv('S3_BUCKET')}")
        logger.info(f"S3 Config Debug - resolved bucket: {bucket}")

        # Force fallback if bucket is still None
        if not bucket:
            bucket = "circles-media-259c"  # Hardcode the known bucket as last resort
            logger.warning(
                f"S3 bucket was None, using hardcoded fallback: {bucket}")

        if not region:
            region = "us-east-1"  # Hardcode the known region as last resort
            logger.warning(
                f"S3 region was None, using hardcoded fallback: {region}")

        try:
            use_path_style = settings.s3_use_path_style if use_path_style_env is None else str(
                use_path_style_env).lower() in ("1", "true", "yes")
        except Exception:
            use_path_style = settings.s3_use_path_style
        return {
            "bucket": bucket,
            "region": region,
            "endpoint": endpoint,
            "public_base": public_base,
            "use_path_style": use_path_style,
            "access_key_id": settings.s3_access_key_id,
            "secret_access_key": settings.s3_secret_access_key,
        }

    @staticmethod
    async def save_review_photo(review_id: int, filename: str, content: bytes) -> str:
        _validate_image_or_raise(filename, content)
        if settings.storage_backend == "s3":
            return await StorageService._save_s3(review_id, filename, content)
        return await StorageService._save_local(review_id, filename, content)

    @staticmethod
    async def save_checkin_photo(check_in_id: int, filename: str, content: bytes) -> str:
        _validate_image_or_raise(filename, content)
        if settings.storage_backend == "s3":
            return await StorageService._save_checkin_s3(check_in_id, filename, content)
        return await StorageService._save_checkin_local(check_in_id, filename, content)

    @staticmethod
    async def _save_local(review_id: int, filename: str, content: bytes) -> str:
        media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
        target_dir = os.path.join(media_root, "reviews", str(review_id))
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        with open(target_path, "wb") as f:
            f.write(content)
        return f"/media/reviews/{review_id}/{filename}"

    @staticmethod
    async def delete_review_photo(review_id: int, filename: str) -> None:
        if settings.storage_backend == "s3":
            import boto3
            cfg = StorageService._resolved_s3_config()
            session = boto3.session.Session(
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=cfg["region"],
            )
            s3 = session.client("s3", endpoint_url=cfg["endpoint"])
            key = f"reviews/{review_id}/{filename}"
            try:
                s3.delete_object(Bucket=cfg["bucket"], Key=key)
            except Exception as e:
                logger.error(f"Failed to delete S3 review photo {key}: {e}")
        else:
            media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
            path = os.path.join(media_root, "reviews",
                                str(review_id), filename)
            try:
                os.remove(path)
            except FileNotFoundError:
                logger.warning(f"Review photo file not found: {path}")
            except Exception as e:
                logger.error(
                    f"Failed to delete local review photo {path}: {e}")

    @staticmethod
    async def _save_s3(review_id: int, filename: str, content: bytes) -> str:
        import boto3
        from botocore.config import Config as BotoConfig
        import asyncio

        cfg = StorageService._resolved_s3_config()

        if not cfg["bucket"]:
            raise ValueError(
                "S3 bucket is not configured. Set S3_BUCKET or APP_S3_BUCKET.")

        def _upload_to_s3():
            session = boto3.session.Session(
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=cfg["region"],
            )
            s3 = session.client(
                "s3",
                endpoint_url=cfg["endpoint"],
                config=BotoConfig(
                    s3={"addressing_style": "path" if cfg["use_path_style"] else "auto"}),
            )
            key = f"reviews/{review_id}/{filename}"
            # Emergency fallback
            bucket_name = cfg["bucket"] or "circles-media-259c"
            s3.put_object(Bucket=bucket_name, Key=key,
                          Body=content, ContentType=_guess_content_type(filename))
            return key

        # Run S3 upload in thread pool to avoid blocking event loop
        key = await asyncio.to_thread(_upload_to_s3)

        # Return the S3 key instead of full URL - signed URLs will be generated on-demand
        return key

    @staticmethod
    async def _save_checkin_local(check_in_id: int, filename: str, content: bytes) -> str:
        media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
        target_dir = os.path.join(media_root, "checkins", str(check_in_id))
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        with open(target_path, "wb") as f:
            f.write(content)
        return f"/media/checkins/{check_in_id}/{filename}"

    @staticmethod
    async def delete_checkin_photo(check_in_id: int, filename: str) -> None:
        if settings.storage_backend == "s3":
            import boto3
            cfg = StorageService._resolved_s3_config()
            session = boto3.session.Session(
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=cfg["region"],
            )
            s3 = session.client("s3", endpoint_url=cfg["endpoint"])
            key = f"checkins/{check_in_id}/{filename}"
            try:
                s3.delete_object(Bucket=cfg["bucket"], Key=key)
            except Exception as e:
                logger.error(f"Failed to delete S3 checkin photo {key}: {e}")
        else:
            media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
            path = os.path.join(media_root, "checkins",
                                str(check_in_id), filename)
            try:
                os.remove(path)
            except FileNotFoundError:
                logger.warning(f"Checkin photo file not found: {path}")
            except Exception as e:
                logger.error(
                    f"Failed to delete local checkin photo {path}: {e}")

    @staticmethod
    async def _save_checkin_s3(check_in_id: int, filename: str, content: bytes) -> str:
        import boto3
        from botocore.config import Config as BotoConfig
        import asyncio

        cfg = StorageService._resolved_s3_config()

        if not cfg["bucket"]:
            raise ValueError(
                "S3 bucket is not configured. Set S3_BUCKET or APP_S3_BUCKET.")

        def _upload_checkin_to_s3():
            session = boto3.session.Session(
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=cfg["region"],
            )
            s3 = session.client(
                "s3",
                endpoint_url=cfg["endpoint"],
                config=BotoConfig(
                    s3={"addressing_style": "path" if cfg["use_path_style"] else "auto"}),
            )
            key = f"checkins/{check_in_id}/{filename}"
            # Emergency fallback
            bucket_name = cfg["bucket"] or "circles-media-259c"
            s3.put_object(Bucket=bucket_name, Key=key,
                          Body=content, ContentType=_guess_content_type(filename))
            return key

        # Run S3 upload in thread pool to avoid blocking event loop
        key = await asyncio.to_thread(_upload_checkin_to_s3)

        # Return the S3 key instead of full URL - signed URLs will be generated on-demand
        return key

    @staticmethod
    def generate_signed_url(s3_key: str, expiration: int = 3600) -> str:
        """
        Generate a signed URL for accessing an S3 object.

        Args:
            s3_key: The S3 object key (e.g., "checkins/34/test.png")
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Signed URL that allows temporary access to the S3 object
        """
        import boto3
        from botocore.exceptions import ClientError

        cfg = StorageService._resolved_s3_config()

        if not cfg["bucket"]:
            raise ValueError("S3 bucket is not configured")

        try:
            session = boto3.session.Session(
                aws_access_key_id=cfg["access_key_id"],
                aws_secret_access_key=cfg["secret_access_key"],
                region_name=cfg["region"],
            )
            s3_client = session.client("s3", endpoint_url=cfg["endpoint"])

            bucket_name = cfg["bucket"] or "circles-media-259c"

            # Generate signed URL
            signed_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )

            return signed_url

        except ClientError as e:
            logger.error(f"Error generating signed URL for {s3_key}: {e}")
            raise ValueError(f"Failed to generate signed URL: {e}")


def _validate_image_or_raise(filename: str, content: bytes) -> None:
    # Size cap from settings (photo_max_mb)
    from ..config import settings
    max_bytes = int(settings.photo_max_mb) * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError("File too large; max 10MB")
    # Content type by extension must be image
    ctype = _guess_content_type(filename)
    if not ctype.startswith("image/"):
        raise ValueError("Unsupported file type")
    # Attempt to open with Pillow to validate image
    try:
        from PIL import Image
        import io
        Image.open(io.BytesIO(content)).verify()
    except Exception:
        raise ValueError("Invalid image file")


def _guess_content_type(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
