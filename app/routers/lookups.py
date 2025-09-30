"""
Lookup endpoints for cities, countries, and neighborhoods.
Uses external APIs (GeoNames, Nominatim) for fast, comprehensive data.
"""
import json
import logging
import httpx
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct

from ..database import get_db
from ..models import Place
from ..config import settings

router = APIRouter(prefix="/lookups", tags=["lookups"])
logger = logging.getLogger(__name__)


@router.get("/cities", response_model=List[dict])
async def get_cities_for_filter(
    country: str = Query("SA", description="2-letter country code (SA, AE, etc.)"),
    limit: int = Query(50, ge=1, le=200, description="Max cities to return")
):
    """
    Get cities using GeoNames API - fast, free, comprehensive.
    
    **Authentication Required:** No
    
    Uses GeoNames to get major cities for the specified country.
    Returns cities sorted by population (largest first).
    
    **Free tier**: 30,000 requests/day
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # GeoNames API - get cities by country
            # Note: Register for free at http://www.geonames.org/login to get username
            # For now using 'demo' username (limited, but works for testing)
            url = "http://api.geonames.org/searchJSON"
            params = {
                "country": country,
                "featureClass": "P",  # Populated places (cities)
                "featureCode": "PPLA",  # First-order administrative divisions (major cities)
                "maxRows": limit,
                "orderby": "population",
                "username": "demo"  # TODO: Get your own free username from geonames.org
            }
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.error(f"GeoNames API error: {response.status_code}")
                raise HTTPException(status_code=502, detail="Failed to fetch cities")
            
            data = response.json()
            cities = []
            
            for place in data.get('geonames', []):
                cities.append({
                    "name": place.get('name'),
                    "country": place.get('countryCode'),
                    "region": place.get('adminName1'),  # State/Province
                    "population": place.get('population', 0),
                    "latitude": place.get('lat'),
                    "longitude": place.get('lng')
                })
            
            return cities
            
    except httpx.TimeoutException:
        logger.error("GeoNames API timeout")
        raise HTTPException(status_code=504, detail="City lookup timeout")
    except Exception as e:
        logger.error(f"Failed to get cities from GeoNames: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cities")


@router.get("/cities/all", response_model=List[str])
async def get_all_cities(
    country: str | None = Query(None, description="Filter by 2-letter country code"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all cities from database where we have places.
    
    **Authentication Required:** No
    
    Returns cities that actually have places in our database.
    Optionally filter by country code.
    """
    try:
        query = select(distinct(Place.city)).where(Place.city.isnot(None))
        
        if country:
            query = query.where(Place.country == country.upper())
        
        query = query.order_by(Place.city)
        
        result = await db.execute(query)
        cities = [city for city, in result.all() if city]
        
        return cities
    except Exception as e:
        logger.error(f"Failed to get cities from database: {e}")
        return []


@router.get("/neighborhoods", response_model=List[dict])
async def get_neighborhoods_for_filter(
    city: str = Query(..., description="City name"),
    lat: float | None = Query(None, description="City latitude (if known)"),
    lng: float | None = Query(None, description="City longitude (if known)"),
):
    """
    Get neighborhoods using GeoNames API - fast and free.
    
    **Authentication Required:** No
    
    Returns neighborhoods/districts for a given city using GeoNames.
    Much faster than querying database.
    
    **Free tier**: 30,000 requests/day
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # GeoNames API - find nearby populated places (neighborhoods)
            url = "http://api.geonames.org/searchJSON"
            
            params = {
                "q": city,
                "featureClass": "P",  # Populated places
                "featureCode": "PPLX",  # Section of populated place (neighborhoods)
                "maxRows": 50,
                "username": "demo"  # TODO: Get your own free username
            }
            
            # If we have lat/lng, use findNearbyPlaceNameJSON for better results
            if lat and lng:
                url = "http://api.geonames.org/findNearbyPlaceNameJSON"
                params = {
                    "lat": lat,
                    "lng": lng,
                    "radius": 20,  # 20km radius
                    "maxRows": 50,
                    "style": "MEDIUM",
                    "username": "demo"
                }
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.error(f"GeoNames API error: {response.status_code}")
                return []
            
            data = response.json()
            neighborhoods = []
            
            for place in data.get('geonames', []):
                # Skip if it's the same as the city name
                if place.get('name') != city:
                    neighborhoods.append({
                        "name": place.get('name'),
                        "distance": place.get('distance'),  # km from center
                        "population": place.get('population', 0)
                    })
            
            # Sort by distance (closest first)
            neighborhoods.sort(key=lambda x: x.get('distance', 999))
            
            return neighborhoods[:50]  # Limit to 50
            
    except Exception as e:
        logger.error(f"Failed to get neighborhoods from GeoNames: {e}")
        return []
