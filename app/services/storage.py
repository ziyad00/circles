import os
from typing import Optional

from ..config import settings


class StorageService:
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
            session = boto3.session.Session(
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=settings.s3_region,
            )
            s3 = session.client("s3", endpoint_url=settings.s3_endpoint_url)
            key = f"reviews/{review_id}/{filename}"
            try:
                s3.delete_object(Bucket=settings.s3_bucket, Key=key)
            except Exception:
                pass
        else:
            media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
            path = os.path.join(media_root, "reviews",
                                str(review_id), filename)
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    @staticmethod
    async def _save_s3(review_id: int, filename: str, content: bytes) -> str:
        import boto3
        from botocore.config import Config as BotoConfig

        session = boto3.session.Session(
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )
        s3 = session.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            config=BotoConfig(
                s3={"addressing_style": "path" if settings.s3_use_path_style else "auto"}),
        )
        key = f"reviews/{review_id}/{filename}"
        s3.put_object(Bucket=settings.s3_bucket, Key=key,
                      Body=content, ContentType=_guess_content_type(filename))
        if settings.s3_public_base_url:
            return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
        # fallback to virtual-hosted style if possible
        host = settings.s3_endpoint_url.rstrip(
            '/') if settings.s3_endpoint_url else f"https://{settings.s3_bucket}.s3.amazonaws.com"
        return f"{host}/{settings.s3_bucket}/{key}" if settings.s3_use_path_style else f"https://{settings.s3_bucket}.s3.amazonaws.com/{key}"

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
            session = boto3.session.Session(
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=settings.s3_region,
            )
            s3 = session.client("s3", endpoint_url=settings.s3_endpoint_url)
            key = f"checkins/{check_in_id}/{filename}"
            try:
                s3.delete_object(Bucket=settings.s3_bucket, Key=key)
            except Exception:
                pass
        else:
            media_root = os.path.abspath(os.path.join(os.getcwd(), "media"))
            path = os.path.join(media_root, "checkins",
                                str(check_in_id), filename)
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    @staticmethod
    async def _save_checkin_s3(check_in_id: int, filename: str, content: bytes) -> str:
        import boto3
        from botocore.config import Config as BotoConfig

        session = boto3.session.Session(
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )
        s3 = session.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            config=BotoConfig(
                s3={"addressing_style": "path" if settings.s3_use_path_style else "auto"}),
        )
        key = f"checkins/{check_in_id}/{filename}"
        s3.put_object(Bucket=settings.s3_bucket, Key=key,
                      Body=content, ContentType=_guess_content_type(filename))
        if settings.s3_public_base_url:
            return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
        host = settings.s3_endpoint_url.rstrip(
            '/') if settings.s3_endpoint_url else f"https://{settings.s3_bucket}.s3.amazonaws.com"
        return f"{host}/{settings.s3_bucket}/{key}" if settings.s3_use_path_style else f"https://{settings.s3_bucket}.s3.amazonaws.com/{key}"


def _guess_content_type(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def _validate_image_or_raise(filename: str, content: bytes) -> None:
    # Size cap 10 MB
    max_bytes = 10 * 1024 * 1024
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
