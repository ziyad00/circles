"""
Debug endpoints for troubleshooting AWS deployment issues
"""

import logging
import os
from fastapi import APIRouter
from typing import Dict, Any

from ..config import settings

router = APIRouter(prefix="/debug", tags=["debug"])

logger = logging.getLogger(__name__)


@router.get("/config")
async def debug_config() -> Dict[str, Any]:
    """
    Debug endpoint to check configuration values.

    **Authentication Required:** No
    """
    return {
        "foursquare_api_key": settings.foursquare_api_key[:10] + "..." if settings.foursquare_api_key else None,
        "foursquare_api_key_length": len(settings.foursquare_api_key) if settings.foursquare_api_key else 0,
        "foursquare_client_id": settings.foursquare_client_id[:10] + "..." if settings.foursquare_client_id else None,
        "foursquare_client_secret": settings.foursquare_client_secret[:10] + "..." if settings.foursquare_client_secret else None,
        "fsq_trending_enabled": settings.fsq_trending_enabled,
        "fsq_trending_override": settings.fsq_trending_override,
        "fsq_use_real_trending": settings.fsq_use_real_trending,
        "fsq_trending_radius_m": settings.fsq_trending_radius_m,
        "database_url": settings.database_url[:20] + "..." if settings.database_url else None,
        "environment_variables": {
            "APP_FOURSQUARE_API_KEY": os.environ.get("APP_FOURSQUARE_API_KEY", "NOT_SET")[:10] + "..." if os.environ.get("APP_FOURSQUARE_API_KEY") else "NOT_SET",
            "FOURSQUARE_API_KEY": os.environ.get("FOURSQUARE_API_KEY", "NOT_SET")[:10] + "..." if os.environ.get("FOURSQUARE_API_KEY") else "NOT_SET",
            "FOURSQUARE_CLIENT_ID": os.environ.get("FOURSQUARE_CLIENT_ID", "NOT_SET")[:10] + "..." if os.environ.get("FOURSQUARE_CLIENT_ID") else "NOT_SET",
            "FOURSQUARE_CLIENT_SECRET": os.environ.get("FOURSQUARE_CLIENT_SECRET", "NOT_SET")[:10] + "..." if os.environ.get("FOURSQUARE_CLIENT_SECRET") else "NOT_SET",
        }
    }


@router.get("/foursquare-test")
async def debug_foursquare_test() -> Dict[str, Any]:
    """
    Debug endpoint to test Foursquare API connectivity.

    **Authentication Required:** No
    """
    from ..services.place_data_service_v2 import enhanced_place_data_service
    import asyncio

    try:
        # Test with NYC coordinates
        places = await enhanced_place_data_service.fetch_foursquare_trending(
            lat=40.7128,
            lon=-74.0060,
            limit=3
        )

        return {
            "success": True,
            "places_count": len(places),
            "api_key_configured": bool(settings.foursquare_api_key),
            "api_key_length": len(settings.foursquare_api_key) if settings.foursquare_api_key else 0,
            "places": [
                {
                    "name": place.get("name", "Unknown"),
                    "latitude": place.get("latitude"),
                    "longitude": place.get("longitude"),
                    "categories": place.get("categories", "")
                }
                for place in places[:3]
            ] if places else []
        }
    except Exception as e:
        logger.error(f"Foursquare API test failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "api_key_configured": bool(settings.foursquare_api_key),
            "api_key_length": len(settings.foursquare_api_key) if settings.foursquare_api_key else 0,
        }
