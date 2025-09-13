## Collections API – Requests and Responses

All authenticated requests require the header:

```
Authorization: Bearer <token>
```

### Create collection

Request

```http
POST /collections/
Content-Type: application/json

{
  "name": "My Favorites",
  "description": "Best spots",
  "is_public": true
}
```

Response

```json
{
  "id": 123,
  "user_id": 49,
  "name": "My Favorites",
  "description": "Best spots",
  "is_public": true,
  "created_at": "2025-09-13T22:33:04.457007Z",
  "updated_at": null
}
```

### List collections (paginated)

Request

```http
GET /collections?limit=20&offset=0
```

Response

```json
{
  "items": [
    {
      "id": 123,
      "user_id": 49,
      "name": "My Favorites",
      "description": "Best spots",
      "is_public": true,
      "created_at": "2025-09-13T22:33:04.457007Z",
      "updated_at": null
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### Get collection by id

Request

```http
GET /collections/123
```

Response

```json
{
  "id": 123,
  "user_id": 49,
  "name": "My Favorites",
  "description": "Best spots",
  "is_public": true,
  "created_at": "2025-09-13T22:33:04.457007Z",
  "updated_at": null
}
```

### Update collection

Request

```http
PUT /collections/123
Content-Type: application/json

{
  "name": "My Favorites v2",
  "description": "Updated description",
  "is_public": false
}
```

Response

```json
{
  "id": 123,
  "user_id": 49,
  "name": "My Favorites v2",
  "description": "Updated description",
  "is_public": false,
  "created_at": "2025-09-13T22:33:04.457007Z",
  "updated_at": "2025-09-13T23:10:00Z"
}
```

### Delete collection

Request

```http
DELETE /collections/123
```

Response: 204 No Content

### Add place to collection

Request

```http
POST /collections/123/places/2
```

Response

```json
{
  "message": "Place added to collection",
  "id": 777
}
```

### Remove place from collection

Request

```http
DELETE /collections/123/places/2
```

Response: 204 No Content

### List places in collection (paginated – rich data)

Request

```http
GET /collections/123/places?limit=20&offset=0
```

Response

```json
{
  "items": [
    {
      "id": 777,
      "collection_id": 123,
      "place_id": 2,
      "place_name": "Tamimi",
      "place_address": null,
      "place_city": null,
      "place_latitude": 24.7368857,
      "place_longitude": 46.6839908,
      "place_rating": null,
      "place_photo_url": null,
      "checkin_count": 0,
      "user_checkin_photos": [],
      "added_at": "2025-09-13T23:35:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### Items alias (same as places)

Request

```http
GET /collections/123/items?limit=20&offset=0
```

Response: same as GET /collections/{id}/places

### Minimal items list (non‑paginated, simple shape)

Request

```http
GET /collections/123/items/list
```

Response

```json
[
  {
    "collection_place_id": 777,
    "place_id": 2,
    "place_name": "Tamimi",
    "address": null,
    "city": null,
    "latitude": 24.7368857,
    "longitude": 46.6839908,
    "rating": null,
    "description": null,
    "categories": "shop:supermarket",
    "photos": [],
    "added_at": "2025-09-13T23:35:00Z"
  }
]
```

### Collections summary (minimal, with random photos)

Request

```http
GET /collections/summary
```

Response

```json
[
  {
    "id": 123,
    "name": "My Favorites v2",
    "count": 1,
    "photos": []
  }
]
```

---

## Saved Collections (Saved Places) – Requests and Responses

### List saved collection names

Request

```http
GET /places/saved/collections
```

Response

```json
["Favorites", "Coffee Spots"]
```

### Get a saved collection (summary with random photos)

Request

```http
GET /places/saved/collections/Coffee%20Spots
```

Response

```json
{
  "name": "Coffee Spots",
  "count": 5,
  "photos": [
    "https://signed.example/photo1.jpg",
    "https://signed.example/photo2.jpg"
  ]
}
```

### Get items in a saved collection

Request

```http
GET /places/saved/collections/Coffee%20Spots/items
```

Response

```json
[
  {
    "saved_place_id": 501,
    "place_id": 2,
    "place_name": "Tamimi",
    "address": null,
    "city": null,
    "latitude": 24.7368857,
    "longitude": 46.6839908,
    "rating": null,
    "description": null,
    "categories": "shop:supermarket",
    "photos": [],
    "saved_at": "2025-09-13T23:35:00Z"
  }
]
```

### List saved places (optional collection filter)

Request

```http
GET /places/saved/me?collection=Coffee%20Spots&limit=20&offset=0
```

Response

```json
{
  "items": [
    {
      "id": 501,
      "user_id": 49,
      "place_id": 2,
      "list_name": "Coffee Spots",
      "created_at": "2025-09-13T23:35:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```
