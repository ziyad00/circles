# Missing Backend Endpoints Analysis

Based on the enhanced API analysis, here are the actual missing backend endpoints that need to be implemented:

## Critical Missing Endpoints

### 1. Chat Rooms Endpoints

**Frontend calls:**

- `GET /places/{placeId}/chat-rooms`
- `POST /places/{placeId}/chat-rooms`

**Request Body (POST):** `request.toJson()`

**Files:** `frontend/lib/scr/feature/locationChat/data/data_sources/remote/locationChat_remote_datasource.dart`

**Status:** ❌ **MISSING** - These endpoints don't exist in the backend

### 2. Collection Items Endpoint

**Frontend calls:**

- `GET /collections/{collectionId}/items`

**Files:** `frontend/lib/scr/feature/list/data/data_sources/remote/list_remote_datasource.dart`

**Status:** ❌ **MISSING** - This endpoint doesn't exist in the backend

### 3. Collection Update Endpoint

**Frontend calls:**

- `PUT /collections/{collectionId}`

**Request Body:** `requestModel.toQuery()`

**Files:** `frontend/lib/scr/feature/list/data/data_sources/remote/list_remote_datasource.dart`

**Status:** ❌ **MISSING** - This endpoint doesn't exist in the backend

## Endpoints That Exist But Have Issues

### 1. Follow Endpoints

**Frontend calls:**

- `POST /follow/{userId}`

**Backend exists:**

- `POST /follow/{user_id}`

**Status:** ⚠️ **PARAMETER MISMATCH** - Parameter name differs (`userId` vs `user_id`)

### 2. User Profile Endpoints

**Frontend calls:**

- `GET /users/{userId}/check-ins`
- `GET /users/{userId}/media`
- `GET /users/{userId}/collections`

**Backend exists:**

- `GET /users/{user_id}/check-ins`
- `GET /users/{user_id}/media`
- `GET /users/{user_id}/collections`

**Status:** ⚠️ **PARAMETER MISMATCH** - Parameter name differs (`userId` vs `user_id`)

## Recommendations

### Immediate Actions Required:

1. **Implement Chat Rooms Endpoints:**

   ```python
   @router.get("/{place_id}/chat-rooms")
   @router.post("/{place_id}/chat-rooms")
   ```

2. **Implement Collection Items Endpoint:**

   ```python
   @router.get("/{collection_id}/items")
   ```

3. **Implement Collection Update Endpoint:**
   ```python
   @router.put("/{collection_id}")
   ```

### Parameter Name Standardization:

The frontend uses `userId` while the backend uses `user_id`. This should be standardized. Options:

- Update frontend to use `user_id`
- Update backend to use `userId`
- Make both work (less ideal)

### Files to Update:

1. **Backend:**

   - `circles/app/routers/places.py` - Add chat rooms endpoints
   - `circles/app/routers/collections.py` - Add items and update endpoints

2. **Frontend:**
   - Update parameter names in API calls to match backend
   - Or update backend parameter names to match frontend

## Next Steps:

1. Implement the missing endpoints
2. Standardize parameter naming
3. Test all endpoints
4. Update API documentation
