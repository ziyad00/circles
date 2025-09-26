from fastapi import APIRouter
from ..config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "debug": settings.debug}

@router.get("/debug/photos", include_in_schema=False)
async def debug_checkin_photos():
    """Debug endpoint to check CheckInPhoto data"""
    from ..database import get_db
    from sqlalchemy import text

    try:
        async for db in get_db():
            # First find all users with similar phone numbers or username ziyad
            users_result = await db.execute(text("""
                SELECT id, name, phone, email, username
                FROM users
                WHERE phone LIKE '%535667585%' OR phone LIKE '%0535667585%' OR username = 'ziyad'
                ORDER BY id
            """))

            users = users_result.fetchall()

            # Check check-ins for any matching user (including photo_url field)
            checkins_result = await db.execute(text("""
                SELECT ci.id, ci.user_id, ci.place_id, ci.created_at, ci.photo_url, ci.note,
                       u.phone, u.name, u.username
                FROM check_ins ci
                JOIN users u ON ci.user_id = u.id
                WHERE u.phone LIKE '%535667585%' OR u.phone LIKE '%0535667585%' OR u.username = 'ziyad'
                ORDER BY ci.created_at DESC
                LIMIT 10
            """))

            checkins = checkins_result.fetchall()

            # Check if there are any check-in photos for matching users
            result = await db.execute(text("""
                SELECT
                    cip.id, cip.url, cip.created_at,
                    ci.id as checkin_id, ci.user_id, ci.place_id,
                    u.name as user_name, u.phone, u.username
                FROM check_in_photos cip
                JOIN check_ins ci ON cip.check_in_id = ci.id
                JOIN users u ON ci.user_id = u.id
                WHERE u.phone LIKE '%535667585%' OR u.phone LIKE '%0535667585%' OR u.username = 'ziyad'
                ORDER BY cip.created_at DESC
                LIMIT 10
            """))

            photos = result.fetchall()

            # Also check for any orphaned photos in CheckInPhoto table
            all_photos_result = await db.execute(text("""
                SELECT cip.id, cip.check_in_id, cip.url, cip.created_at
                FROM check_in_photos cip
                ORDER BY cip.created_at DESC
                LIMIT 20
            """))

            all_photos = all_photos_result.fetchall()

            # Total check-ins count
            count_result = await db.execute(text("""
                SELECT COUNT(*) as total_checkins
                FROM check_ins ci
                JOIN users u ON ci.user_id = u.id
                WHERE u.phone LIKE '%535667585%' OR u.phone LIKE '%0535667585%' OR u.username = 'ziyad'
            """))

            total_checkins = count_result.fetchone()[0]

            # Also check what places exist in database
            places_result = await db.execute(text("""
                SELECT id, name, address, created_at
                FROM places
                ORDER BY created_at DESC
                LIMIT 10
            """))

            places = places_result.fetchall()

            return {
                "search_criteria": "phone LIKE '%535667585%' OR username = 'ziyad'",
                "places_in_db": [
                    {
                        "id": place.id,
                        "name": place.name,
                        "address": place.address,
                        "created_at": str(place.created_at)
                    }
                    for place in places
                ],
                "users_found": [
                    {
                        "id": user.id,
                        "name": user.name,
                        "phone": user.phone,
                        "username": user.username,
                        "email": user.email
                    }
                    for user in users
                ],
                "total_checkins": total_checkins,
                "checkins": [
                    {
                        "checkin_id": checkin.id,
                        "user_id": checkin.user_id,
                        "place_id": checkin.place_id,
                        "created_at": str(checkin.created_at),
                        "photo_url": checkin.photo_url,
                        "note": checkin.note,
                        "phone": checkin.phone,
                        "name": checkin.name,
                        "username": checkin.username
                    }
                    for checkin in checkins
                ],
                "total_photos": len(photos),
                "photos": [
                    {
                        "photo_id": photo.id,
                        "url": photo.url,
                        "created_at": str(photo.created_at),
                        "checkin_id": photo.checkin_id,
                        "user_id": photo.user_id,
                        "user_name": photo.user_name,
                        "username": photo.username,
                        "place_id": photo.place_id
                    }
                    for photo in photos
                ],
                "all_photos_in_db": len(all_photos),
                "all_photos_list": [
                    {
                        "photo_id": photo.id,
                        "checkin_id": photo.check_in_id,
                        "url": photo.url,
                        "created_at": str(photo.created_at)
                    }
                    for photo in all_photos
                ]
            }
    except Exception as e:
        return {"error": str(e), "details": "Failed to query database"}
