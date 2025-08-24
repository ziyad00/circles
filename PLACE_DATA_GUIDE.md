# 🏢 Place Data Integration Guide

## Overview

The Circles application now supports comprehensive place data integration with multiple external sources. This guide covers all the options for getting rich place data into your application.

## 🚀 **Recommended Approach: Multi-Source Integration**

### **1. Google Places API** (Most Comprehensive)

**Best for:** Production applications with budget for API costs

**Features:**

- ✅ Rich place data (ratings, photos, hours, contact info)
- ✅ High accuracy and up-to-date information
- ✅ Extensive place categories and types
- ✅ Popular times and crowd data
- ✅ Detailed reviews and ratings

**Setup:**

```bash
# Add to your .env file
APP_GOOGLE_PLACES_API_KEY=your_google_places_api_key_here
```

**Cost:** ~$17 per 1000 requests (very reasonable for most apps)

### **2. OpenStreetMap + Nominatim** (Free)

**Best for:** Development, testing, or budget-conscious applications

**Features:**

- ✅ Completely free
- ✅ Good coverage worldwide
- ✅ Basic place information
- ✅ Community-maintained data

**Setup:**

```bash
# Already enabled by default
APP_USE_OPENSTREETMAP=true
```

### **3. Foursquare Places API** (Social Features)

**Best for:** Social check-in features and tips

**Features:**

- ✅ Social check-in data
- ✅ User tips and recommendations
- ✅ Venue photos and details
- ✅ Popular times and trends

**Setup:**

```bash
# Add to your .env file
APP_FOURSQUARE_API_KEY=your_foursquare_api_key_here
```

## 📡 **New API Endpoints**

### **1. Search External Places**

```http
GET /places/search/external?lat=37.7749&lon=-122.4194&radius=5000&query=coffee&types=restaurant,cafe
```

**Response:**

```json
[
  {
    "id": 1,
    "name": "Blue Bottle Coffee",
    "address": "66 Mint St, San Francisco, CA",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "rating": 4.5,
    "categories": "coffee,cafe,restaurant",
    "external_id": "ChIJ...",
    "data_source": "google",
    "website": "https://bluebottlecoffee.com",
    "phone": "+1-415-555-0123"
  }
]
```

### **2. Enrich Place Data**

```http
GET /places/1/enrich
```

**Response:**

```json
{
  "id": 1,
  "name": "Blue Bottle Coffee",
  "rating": 4.5,
  "categories": "coffee,cafe,restaurant",
  "website": "https://bluebottlecoffee.com",
  "phone": "+1-415-555-0123",
  "metadata": {
    "opening_hours": ["Monday: 7:00 AM – 6:00 PM", "Tuesday: 7:00 AM – 6:00 PM"],
    "price_level": 2,
    "user_ratings_total": 1250,
    "photos": [...],
    "last_updated": "google"
  },
  "data_source": "google",
  "enriched": true
}
```

### **3. Place Suggestions**

```http
GET /places/suggestions/external?query=coffee&lat=37.7749&lon=-122.4194&limit=10
```

## 🔧 **Implementation Examples**

### **Frontend Integration (JavaScript)**

```javascript
// Search for places near user location
async function searchNearbyPlaces(lat, lon, query = null) {
  const params = new URLSearchParams({
    lat: lat,
    lon: lon,
    radius: 5000,
    types: "restaurant,cafe,bar",
  });

  if (query) params.append("query", query);

  const response = await fetch(`/places/search/external?${params}`);
  const places = await response.json();

  return places;
}

// Enrich place with additional data
async function enrichPlace(placeId) {
  const response = await fetch(`/places/${placeId}/enrich`);
  const enrichedPlace = await response.json();

  return enrichedPlace;
}

// Get place suggestions for autocomplete
async function getPlaceSuggestions(query, lat = null, lon = null) {
  const params = new URLSearchParams({
    query: query,
    limit: 10,
  });

  if (lat && lon) {
    params.append("lat", lat);
    params.append("lon", lon);
  }

  const response = await fetch(`/places/suggestions/external?${params}`);
  const suggestions = await response.json();

  return suggestions;
}
```

### **Mobile App Integration**

```swift
// iOS Swift example
func searchPlaces(latitude: Double, longitude: Double, query: String?) async throws -> [Place] {
    var components = URLComponents(string: "\(baseURL)/places/search/external")!
    components.queryItems = [
        URLQueryItem(name: "lat", value: String(latitude)),
        URLQueryItem(name: "lon", value: String(longitude)),
        URLQueryItem(name: "radius", value: "5000")
    ]

    if let query = query {
        components.queryItems?.append(URLQueryItem(name: "query", value: query))
    }

    let (data, _) = try await URLSession.shared.data(from: components.url!)
    return try JSONDecoder().decode([Place].self, from: data)
}
```

## 🎯 **Use Cases & Recommendations**

### **For Development/Testing:**

- ✅ Use OpenStreetMap (free, no API key needed)
- ✅ Good for prototyping and testing
- ✅ Sufficient for basic place discovery

### **For Production Apps:**

- ✅ Start with Google Places API
- ✅ Fallback to OpenStreetMap if Google fails
- ✅ Consider Foursquare for social features

### **For Budget-Conscious Apps:**

- ✅ Use OpenStreetMap as primary source
- ✅ Add Google Places for premium features
- ✅ Implement smart caching to reduce API calls

## 🔄 **Data Flow**

1. **User searches for places** → Calls `/places/search/external`
2. **System searches multiple sources** → Google Places + OpenStreetMap
3. **Results are deduplicated** → Removes duplicate places
4. **Places are synced to database** → Creates/updates local records
5. **User selects a place** → Can enrich with `/places/{id}/enrich`
6. **Rich data is cached** → Stored in `metadata` JSON field

## 📊 **Data Quality Comparison**

| Feature         | Google Places | OpenStreetMap | Foursquare |
| --------------- | ------------- | ------------- | ---------- |
| **Accuracy**    | ⭐⭐⭐⭐⭐    | ⭐⭐⭐⭐      | ⭐⭐⭐⭐   |
| **Coverage**    | ⭐⭐⭐⭐⭐    | ⭐⭐⭐⭐      | ⭐⭐⭐     |
| **Richness**    | ⭐⭐⭐⭐⭐    | ⭐⭐          | ⭐⭐⭐⭐   |
| **Cost**        | 💰💰          | 🆓            | 💰💰       |
| **Social Data** | ⭐⭐          | ⭐            | ⭐⭐⭐⭐⭐ |

## 🚀 **Getting Started**

### **Step 1: Choose Your Data Source**

```bash
# For Google Places (recommended for production)
APP_GOOGLE_PLACES_API_KEY=your_api_key_here

# For OpenStreetMap (free, already enabled)
APP_USE_OPENSTREETMAP=true

# For Foursquare (optional)
APP_FOURSQUARE_API_KEY=your_api_key_here
```

### **Step 2: Test the Endpoints**

```bash
# Search for coffee shops in San Francisco
curl "http://localhost:8000/places/search/external?lat=37.7749&lon=-122.4194&query=coffee&types=restaurant,cafe"

# Get place suggestions
curl "http://localhost:8000/places/suggestions/external?query=starbucks&lat=37.7749&lon=-122.4194"
```

### **Step 3: Integrate with Your Frontend**

- Use the search endpoint for place discovery
- Use the suggestions endpoint for autocomplete
- Use the enrich endpoint for detailed place information

## 💡 **Pro Tips**

1. **Cache Results**: Implement client-side caching to reduce API calls
2. **Batch Requests**: Group multiple place searches when possible
3. **Fallback Strategy**: Always have OpenStreetMap as a backup
4. **Rate Limiting**: Respect API rate limits and implement exponential backoff
5. **Data Freshness**: Re-enrich places periodically to keep data current

## 🔧 **Advanced Configuration**

### **Custom Place Types**

```python
# In your application code
place_types = ["restaurant", "cafe", "bar", "museum", "park"]
types_param = ",".join(place_types)

# API call
response = await client.get(f"/places/search/external?types={types_param}")
```

### **Geographic Filtering**

```python
# Search within specific radius
radius_meters = 2000  # 2km radius
response = await client.get(f"/places/search/external?radius={radius_meters}")
```

### **Query Optimization**

```python
# Use specific queries for better results
query = "organic coffee shop"  # More specific than just "coffee"
response = await client.get(f"/places/search/external?query={query}")
```

## 🎉 **Summary**

The Circles application now provides a comprehensive place data solution that:

- ✅ **Works out of the box** with OpenStreetMap (free)
- ✅ **Scales to production** with Google Places API
- ✅ **Supports multiple sources** with automatic fallback
- ✅ **Integrates seamlessly** with existing place features
- ✅ **Provides rich data** including ratings, photos, and hours
- ✅ **Supports real-time search** and autocomplete

Choose the approach that best fits your needs and budget, and you'll have a robust place data system that grows with your application!
