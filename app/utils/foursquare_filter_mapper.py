"""
Helper to map frontend filter values to Foursquare API parameters.
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FoursquareFilterMapper:
    """Maps frontend filter values to Foursquare API parameters."""
    
    def __init__(self):
        self._category_map: dict[str, list[str]] = {}
        self._load_mappings()
    
    def _load_mappings(self):
        """Load frontend filter to category ID mappings."""
        try:
            json_path = Path(__file__).parent.parent / 'data' / 'frontend_filter_categories.json'
            with open(json_path, 'r') as f:
                self._category_map = json.load(f)
            logger.info(f"Loaded filter mappings for {len(self._category_map)} filter types")
        except Exception as e:
            logger.warning(f"Failed to load filter mappings: {e}")
            self._category_map = {}
    
    def get_category_ids(self, place_type: Optional[str]) -> Optional[str]:
        """
        Convert a frontend place type filter to Foursquare category IDs.
        
        Args:
            place_type: Frontend filter value (e.g., "Restaurant", "Cafe")
        
        Returns:
            Comma-separated string of category IDs for Foursquare API,
            or None if no mapping exists
        """
        if not place_type:
            return None
        
        # Get the category IDs for this filter
        category_ids = self._category_map.get(place_type, [])
        
        if not category_ids:
            logger.warning(f"No category ID mapping for filter: {place_type}")
            return None
        
        # Return comma-separated string of IDs
        return ','.join(category_ids)


# Global instance
foursquare_filter_mapper = FoursquareFilterMapper()
