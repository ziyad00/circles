"""
Storage service to handle both local and S3 file uploads
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional
import boto3
from botocore.exceptions import ClientError
import logging

from ..config import settings

logger = logging.getLogger(__name__)

class StorageService:
    """Unified storage service supporting local and S3 storage"""

    def __init__(self):
        self.backend = settings.storage_backend
        self.local_media_dir = Path("media")
        self.local_media_dir.mkdir(exist_ok=True)

        # Initialize S3 client if using S3
        if self.backend == "s3":
            self.s3_client = boto3.client(
                's3',
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                endpoint_url=settings.s3_endpoint_url
            )
            self.bucket = settings.s3_bucket
            self.public_base_url = settings.s3_public_base_url or f"https://{self.bucket}.s3.{settings.s3_region}.amazonaws.com"

    async def upload_file(self, file_content: bytes, filename: str, content_type: str) -> str:
        """
        Upload file and return public URL

        Args:
            file_content: The file content as bytes
            filename: Desired filename (will be made unique)
            content_type: MIME type of the file

        Returns:
            Public URL to access the uploaded file
        """
        # Generate unique filename
        file_extension = filename.split('.')[-1] if '.' in filename else ''
        unique_filename = f"{uuid.uuid4()}.{file_extension}" if file_extension else str(uuid.uuid4())

        if self.backend == "s3":
            return await self._upload_to_s3(file_content, unique_filename, content_type)
        else:
            return await self._upload_to_local(file_content, unique_filename)

    async def upload_avatar(self, file_content: bytes, user_id: int, filename: str, content_type: str) -> str:
        """Upload user avatar with specific naming"""
        file_extension = filename.split('.')[-1] if '.' in filename else 'jpg'
        avatar_filename = f"avatar_{user_id}_{uuid.uuid4()}.{file_extension}"

        if self.backend == "s3":
            return await self._upload_to_s3(file_content, f"avatars/{avatar_filename}", content_type)
        else:
            return await self._upload_to_local(file_content, avatar_filename)

    async def _upload_to_s3(self, file_content: bytes, key: str, content_type: str) -> str:
        """Upload file to S3"""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_content,
                ContentType=content_type,
                ACL='public-read'  # Make file publicly accessible
            )

            # Return public URL
            if self.public_base_url:
                return f"{self.public_base_url}/{key}"
            else:
                return f"https://{self.bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"

        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            raise Exception(f"Failed to upload to S3: {e}")

    async def _upload_to_local(self, file_content: bytes, filename: str) -> str:
        """Upload file to local filesystem"""
        file_path = self.local_media_dir / filename

        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)

        return f"/media/{filename}"

    def delete_file(self, file_url: str) -> bool:
        """Delete file from storage"""
        try:
            if self.backend == "s3":
                # Extract key from URL
                if self.public_base_url and file_url.startswith(self.public_base_url):
                    key = file_url[len(self.public_base_url):].lstrip('/')
                    self.s3_client.delete_object(Bucket=self.bucket, Key=key)
                    return True
            else:
                # Local file deletion
                if file_url.startswith('/media/'):
                    filename = file_url[7:]  # Remove '/media/' prefix
                    file_path = self.local_media_dir / filename
                    if file_path.exists():
                        file_path.unlink()
                        return True
            return False
        except Exception as e:
            logger.error(f"File deletion failed: {e}")
            return False

# Global storage service instance
storage_service = StorageService()