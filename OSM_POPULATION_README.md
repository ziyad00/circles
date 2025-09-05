# OpenStreetMap Data Population Scripts

This directory contains scripts to populate missing data for places from OpenStreetMap and other sources.

## 📋 Overview

The OSM data population system enhances place data by fetching missing information like:

- **Websites** and **phone numbers**
- **Opening hours** and **detailed amenities**
- **Photos** from multiple sources (Wikimedia Commons, Flickr, Foursquare)
- **Detailed tags** and **metadata**

## 🛠️ Scripts

### `populate_osm_data.py` - Main Population Script

**Purpose**: Populate missing data for places in the database from OSM and other sources.

**Features**:

- ✅ Fetches missing websites, phones, and amenities from OpenStreetMap
- ✅ Retrieves real photos from Wikimedia Commons, Flickr, and Foursquare
- ✅ Extracts detailed amenities (WiFi, outdoor seating, wheelchair access, etc.)
- ✅ Batch processing with configurable rate limiting
- ✅ Smart OSM element matching algorithm
- ✅ Comprehensive logging and error handling

**Usage**:

```bash
# Populate data for 50 places
python scripts/populate_osm_data.py --limit 50

# Populate data for places in a specific city
python scripts/populate_osm_data.py --limit 100 --city Riyadh

# Check current data completeness status
python scripts/populate_osm_data.py --status
```

**Command Line Options**:

- `--limit N`: Number of places to process (default: 50)
- `--city CITY`: Filter places by city name
- `--status`: Show current data completeness statistics only

### `test_osm_population.py` - Testing Script

**Purpose**: Test the OSM data population functionality without affecting the database.

**Usage**:

```bash
# Run all tests
python scripts/test_osm_population.py
```

**What it tests**:

- OSM element finding and matching
- Data parsing and amenity extraction
- Photo fetching from various sources
- Enrichment workflow simulation

## 🔧 Setup

### Prerequisites

1. **Database Connection**: Ensure database is accessible
2. **API Keys** (Optional but recommended):
   - Foursquare API key for additional photos and data
   - Flickr API key for photo fetching

### Environment Variables

```bash
# Optional: Foursquare API for enhanced data
export FOURSQUARE_API_KEY="your_foursquare_api_key"

# Database connection (configure as needed)
export DATABASE_URL="postgresql+asyncpg://user:pass@host:port/db"
```

## 📊 Data Sources

### Primary Sources

- **OpenStreetMap (OSM)**: Main source for addresses, phones, websites, amenities
- **Nominatim**: OSM geocoding service for place matching
- **Overpass API**: Advanced OSM data querying

### Photo Sources

- **Wikimedia Commons**: Free licensed photos
- **Flickr**: User-generated photos (requires API key)
- **Foursquare**: Venue photos (requires API key)
- **Unsplash**: Placeholder photos as fallback

### Data Types Populated

#### Basic Information

- Website URLs
- Phone numbers
- Opening hours
- Categories and tags

#### Amenities

- WiFi availability
- Outdoor seating
- Wheelchair accessibility
- Parking
- Delivery services
- Takeout options
- Family-friendly features

#### Photos

- Venue exterior/interior photos
- Themed placeholder photos
- High-resolution images with metadata

## 🔄 How It Works

1. **Place Selection**: Identifies places missing key data
2. **OSM Matching**: Uses Nominatim to find matching OSM elements
3. **Data Fetching**: Retrieves detailed data from Overpass API
4. **Photo Collection**: Gathers photos from multiple sources
5. **Data Enrichment**: Updates place records with new information
6. **Quality Assurance**: Validates data quality and completeness

## 📈 Performance

- **Batch Processing**: Processes places in configurable batches
- **Rate Limiting**: Respects API rate limits with delays
- **Error Recovery**: Continues processing even if individual places fail
- **Caching**: Reduces API calls for repeated requests

## 📋 Example Output

```
🚀 Starting OSM data population...
Found 150 places needing data population

Processing places...
✅ Starbucks Coffee: Updated with website, phone, amenities
✅ McDonald's Riyadh: Added photos from Wikimedia
✅ Local Restaurant: Updated opening hours

🎉 Population Complete!
   Places processed: 150
   Places updated: 127
   Success rate: 84.7%
```

## 🧪 Testing

Run the test suite to validate functionality:

```bash
python scripts/test_osm_population.py
```

**Test Results** (example):

```
✅ OSM element finding: Working
✅ Data parsing: Working
✅ Photo fetching: Working
✅ Wikimedia integration: Working (5 photos found)
✅ Enrichment workflow: Working
```

## 🚀 Production Usage

### Initial Setup

```bash
# Check current data status
python scripts/populate_osm_data.py --status

# Run initial population for major cities
python scripts/populate_osm_data.py --limit 500 --city Riyadh
python scripts/populate_osm_data.py --limit 300 --city Jeddah
```

### Ongoing Maintenance

```bash
# Weekly updates for places missing data
python scripts/populate_osm_data.py --limit 100
```

### Monitoring

- Check logs for success rates and error patterns
- Monitor API usage and rate limits
- Track data completeness improvements

## ⚠️ Important Notes

- **Rate Limiting**: Scripts include delays to respect API limits
- **Data Quality**: OSM data quality varies by region and completeness
- **API Keys**: Some features require API keys for full functionality
- **Database Load**: Large batches may impact database performance
- **Testing First**: Always test with small batches before production runs

## 🐛 Troubleshooting

### Common Issues

1. **Database Connection Failed**

   - Check DATABASE_URL configuration
   - Ensure database is running and accessible

2. **OSM API Rate Limited**

   - Reduce batch size or increase delays
   - Use different Overpass endpoints

3. **No Photos Found**

   - This is normal - not all places have public photos
   - Script falls back to placeholder photos

4. **Low Match Scores**
   - OSM data may be incomplete for some regions
   - Consider manual data entry for critical places

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📈 Success Metrics

Track these metrics to measure success:

- **Data Completeness**: Percentage of places with websites, phones, etc.
- **Photo Coverage**: Percentage of places with photos
- **API Success Rate**: Percentage of successful API calls
- **Processing Speed**: Places processed per minute

## 🤝 Contributing

When adding new data sources or features:

1. Add comprehensive tests
2. Include proper error handling
3. Update this documentation
4. Test with various place types and locations

---

**Last Updated**: December 2024
**Version**: 1.0.0
