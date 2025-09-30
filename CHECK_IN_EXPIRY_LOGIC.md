# Check-in Expiry Logic

## Overview
Check-ins have an expiry time, but they behave differently depending on the context:

### 1. **Profile Check-in List** (Historical Record)
- **Endpoint:** `GET /users/{user_id}/check-ins`
- **Behavior:** Shows **ALL check-ins** (active + expired)
- **Purpose:** Serves as a permanent history of user's check-ins
- **Filtering:** Only by visibility permissions, NOT by expiry
- **Example:** User's profile shows all their past check-ins forever

### 2. **Trending Places Count** (Real-time Activity)
- **Endpoint:** `GET /places/trending`
- **Behavior:** Only counts **active (non-expired)** check-ins
- **Purpose:** Show real-time activity at places
- **Filtering:** `created_at >= since` AND `expires_at > now`
- **Example:** Place shows "3 people" only if there are 3 active check-ins

### 3. **Who's Here** (Current Presence)
- **Endpoint:** `GET /places/{place_id}/whos-here`
- **Behavior:** Only shows **active (non-expired)** check-ins
- **Purpose:** Show who is currently at a place
- **Filtering:** `created_at >= window_start` AND `expires_at > now`
- **Example:** Shows list of users currently checked in

## Expiry Configuration
- **Default expiry:** 12 hours (`checkin_expiry_hours` setting)
- **Who's Here window:** 12 hours (`place_chat_window_hours` setting)
- **Trending window:** Configurable (1h, 6h, 24h, 7d, 30d)

## Key Points
1. ✅ Check-ins **never deleted** from database
2. ✅ Profile lists show **all historical check-ins**
3. ✅ Activity counts only show **active check-ins**
4. ✅ Old circles **disappear** when all check-ins expire
5. ✅ Users can always see their **full check-in history**
