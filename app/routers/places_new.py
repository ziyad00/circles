from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas import PaginatedPlaces, PlaceResponse
from ..services.place_data_service_v2 import EnhancedPlaceDataService
from datetime import datetime, timezone
import logging

router = APIRouter(prefix="/places", tags=["places"])
enhanced_place_data_service = EnhancedPlaceDataService()


@router.get("/trending", response_model=PaginatedPlaces)
async def get_trending_places(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    limit: int = Query(
        20, ge=1, le=50, description="Number of places to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get trending places using Foursquare API and save to database.
    **Authentication Required:** No
    """
    print(
        f"🔥 NEW TRENDING ENDPOINT CALLED with lat={lat}, lng={lng}, limit={limit}")

    if lat is None or lng is None:
        raise HTTPException(
            status_code=400, detail="lat and lng are required for trending")

    try:
        # Fetch trending places from Foursquare
        fsq_places = await enhanced_place_data_service.fetch_foursquare_trending(
            lat=lat, lon=lng, limit=limit
        )
        print(f"Got {len(fsq_places)} places from Foursquare API")

        if not fsq_places:
            print("No places returned from Foursquare API")
            return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)

        # Save places to database and get them back with database IDs
        saved_places = await enhanced_place_data_service.save_foursquare_places_to_db(fsq_places, db)
        await db.commit()
        print(f"Saved {len(saved_places)} places to database")

        if saved_places:
            print(
                f"First saved place: ID={saved_places[0].id}, Name={saved_places[0].name}")

        # Convert saved places to PlaceResponse objects
        now_ts = datetime.now(timezone.utc)
        items = []

        for place in saved_places:
            try:
                place_resp = PlaceResponse(
                    id=place.id,  # Use the actual database ID
                    name=place.name or "Unknown",
                    address=place.address,
                    city=place.city,
                    neighborhood=place.neighborhood,
                    latitude=place.latitude,
                    longitude=place.longitude,
                    categories=place.categories,
                    rating=place.rating,
                    price_tier=place.price_tier,
                    created_at=place.created_at or now_ts,
                    photo_url=place.photo_url,
                    recent_checkins_count=0,
                    postal_code=place.postal_code,
                    cross_street=place.cross_street,
                    formatted_address=place.formatted_address,
                    distance_meters=place.distance_meters,
                    venue_created_at=place.venue_created_at,
                    primary_category=place.categories.split(
                        ',')[0] if place.categories else None,
                    category_icons=None,
                    photo_urls=[place.photo_url] if place.photo_url else [],
                    additional_photos=[]
                )
                items.append(place_resp)
            except Exception as e:
                print(
                    f"Failed to map place {place.name if hasattr(place, 'name') else 'Unknown'}: {e}")
                continue

        print(f"Returning {len(items)} places with correct database IDs")
        return PaginatedPlaces(
            items=items,
            total=len(items),
            limit=limit,
            offset=offset
        )

    except Exception as e:
        print(f"Error in trending endpoint: {e}")
        return PaginatedPlaces(items=[], total=0, limit=limit, offset=offset)
