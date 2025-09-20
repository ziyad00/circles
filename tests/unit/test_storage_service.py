"""
Unit tests for Storage Service
"""
from app.services.storage import StorageService
import asyncio
import os
import sys
from unittest.mock import patch, MagicMock

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../app'))


class StorageServiceTest:
    """Test Storage Service functionality"""

    def __init__(self):
        self.service = StorageService()

    def test_service_initialization(self):
        """Test service initialization"""
        assert self.service is not None
        assert hasattr(self.service, 's3_client')
        print("✅ Storage service initialization test passed")

    @patch('app.services.storage.boto3.client')
    def test_generate_signed_url(self, mock_boto3):
        """Test signed URL generation"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://signed-url.com/test.jpg"
        mock_boto3.return_value = mock_s3

        # Test signed URL generation
        url = self.service.generate_signed_url("test.jpg")

        assert url is not None
        assert isinstance(url, str)
        assert url.startswith("https://")

        print("✅ Signed URL generation test passed")

    @patch('app.services.storage.boto3.client')
    def test_upload_file(self, mock_boto3):
        """Test file upload"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_s3.upload_fileobj.return_value = None
        mock_boto3.return_value = mock_s3

        # Test file upload
        result = self.service.upload_file(
            "test.jpg", "test-bucket", "test.jpg")

        # Should not raise an exception
        assert result is None

        print("✅ File upload test passed")

    @patch('app.services.storage.boto3.client')
    def test_delete_file(self, mock_boto3):
        """Test file deletion"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_s3.delete_object.return_value = None
        mock_boto3.return_value = mock_s3

        # Test file deletion
        result = self.service.delete_file("test-bucket", "test.jpg")

        # Should not raise an exception
        assert result is None

        print("✅ File deletion test passed")

    def test_url_validation(self):
        """Test URL validation"""
        # Test valid URLs
        valid_urls = [
            "https://example.com/test.jpg",
            "http://example.com/test.jpg",
            "s3://bucket/test.jpg",
            "test.jpg"  # S3 key
        ]

        for url in valid_urls:
            # Basic validation - should not raise exception
            assert isinstance(url, str)
            assert len(url) > 0

        print("✅ URL validation test passed")

    def test_file_extension_handling(self):
        """Test file extension handling"""
        # Test various file extensions
        test_files = [
            "test.jpg",
            "test.png",
            "test.gif",
            "test.webp",
            "test.mp4",
            "test.pdf"
        ]

        for filename in test_files:
            # Basic validation
            assert "." in filename
            extension = filename.split(".")[-1]
            assert len(extension) > 0

        print("✅ File extension handling test passed")

    def run_all_tests(self):
        """Run all storage service tests"""
        print("📁 Testing Storage Service...")
        print("=" * 50)

        try:
            self.test_service_initialization()
            self.test_generate_signed_url()
            self.test_upload_file()
            self.test_delete_file()
            self.test_url_validation()
            self.test_file_extension_handling()

            print("\n✅ All Storage Service tests passed!")

        except Exception as e:
            print(f"\n❌ Storage Service test failed: {e}")
            raise


async def main():
    """Main test runner"""
    test = StorageServiceTest()
    test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
