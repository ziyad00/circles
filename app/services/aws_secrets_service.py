"""
AWS Secrets Manager Service for retrieving API keys securely
"""
import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import boto3, but handle gracefully if not available
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning(
        "boto3 not available. AWS Secrets Manager will be disabled.")


class AWSSecretsService:
    """Service for retrieving secrets from AWS Secrets Manager"""

    def __init__(self, region_name: str = "us-east-1"):
        self.region_name = region_name
        self._secrets_client = None

    @property
    def secrets_client(self):
        """Lazy initialization of secrets client"""
        if not BOTO3_AVAILABLE:
            return None

        if self._secrets_client is None:
            try:
                self._secrets_client = boto3.client(
                    'secretsmanager', region_name=self.region_name)
                logger.info(
                    "AWS Secrets Manager client initialized successfully")
            except Exception as e:
                logger.warning(
                    f"Could not initialize AWS client: {e}. Will use environment fallback.")
                self._secrets_client = None
        return self._secrets_client

    async def get_foursquare_api_key(self) -> Optional[str]:
        """
        Retrieve Foursquare API key from AWS Secrets Manager or environment fallback

        Returns:
            str: The Foursquare API key if found, None otherwise
        """
        # Try environment variable first (for local dev)
        env_key = os.environ.get('FOURSQUARE_API_KEY')
        if env_key:
            logger.info("Using Foursquare API key from environment variable")
            return env_key

        # Check if boto3 is available
        if not BOTO3_AVAILABLE:
            logger.warning(
                "boto3 not available. Cannot access AWS Secrets Manager.")
            return None

        # Fallback to AWS Secrets Manager
        try:
            if self.secrets_client is None:
                logger.warning(
                    "AWS client not available, falling back to environment (which is empty)")
                return None

            logger.info(
                "Retrieving Foursquare API key from AWS Secrets Manager...")

            response = self.secrets_client.get_secret_value(
                SecretId='circles/dev/foursquare/api-key'
            )

            secret_data = json.loads(response['SecretString'])
            api_key = secret_data.get('api_key')

            if api_key:
                logger.info(
                    f"Successfully retrieved Foursquare API key from AWS Secrets Manager: {api_key[:10]}...")
                return api_key
            else:
                logger.error("Foursquare API key not found in secret data")
                return None

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.warning(
                f"AWS Secrets Manager error ({error_code}): {e}. Falling back to environment variable.")
            return os.environ.get('FOURSQUARE_API_KEY')

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse secret JSON: {e}")
            return os.environ.get('FOURSQUARE_API_KEY')

        except Exception as e:
            logger.error(
                f"Unexpected error retrieving Foursquare API key: {e}")
            return os.environ.get('FOURSQUARE_API_KEY')

    async def get_foursquare_credentials(self) -> dict:
        """
        Retrieve Foursquare client_id and client_secret from AWS Secrets Manager

        Returns:
            dict: Dictionary with 'client_id' and 'client_secret' keys
        """
        # Try environment variables first (for local dev)
        env_client_id = os.environ.get('FOURSQUARE_CLIENT_ID')
        env_client_secret = os.environ.get('FOURSQUARE_CLIENT_SECRET')

        if env_client_id and env_client_secret:
            logger.info(
                "Using Foursquare credentials from environment variables")
            return {
                'client_id': env_client_id,
                'client_secret': env_client_secret
            }

        # Check if boto3 is available
        if not BOTO3_AVAILABLE:
            logger.warning(
                "boto3 not available. Cannot access AWS Secrets Manager.")
            return {}

        # Fallback to AWS Secrets Manager
        try:
            if self.secrets_client is None:
                logger.warning("AWS client not available")
                return {}

            logger.info(
                "Retrieving Foursquare credentials from AWS Secrets Manager...")

            response = self.secrets_client.get_secret_value(
                SecretId='circles/dev/foursquare/credentials'
            )

            secret_data = json.loads(response['SecretString'])
            client_id = secret_data.get('client_id')
            client_secret = secret_data.get('client_secret')

            if client_id and client_secret:
                logger.info(
                    "Successfully retrieved Foursquare credentials from AWS Secrets Manager")
                return {
                    'client_id': client_id,
                    'client_secret': client_secret
                }
            else:
                logger.error("Foursquare credentials not found in secret data")
                return {}

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.warning(f"AWS Secrets Manager error ({error_code}): {e}")
            return {}

        except Exception as e:
            logger.error(
                f"Unexpected error retrieving Foursquare credentials: {e}")
            return {}


# Global instance
aws_secrets_service = AWSSecretsService()
