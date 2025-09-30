"""
Category-based filtering using Foursquare's official taxonomy.
"""
import json
import logging
from pathlib import Path
from typing import Set, Optional

logger = logging.getLogger(__name__)


class CategoryFilter:
    """Filter places using Foursquare category IDs for accurate matching."""

    def __init__(self):
        self._category_map: dict[str, list[str]] = {}
        self._load_categories()

    def _load_categories(self):
        """Load category ID mappings from JSON file."""
        try:
            json_path = Path(__file__).parent.parent / \
                'data' / 'category_filters.json'
            with open(json_path, 'r') as f:
                self._category_map = json.load(f)
            logger.info(
                f"Loaded category filters: {len(self._category_map)} filter types")
        except Exception as e:
            logger.warning(f"Failed to load category filters: {e}")
            # Fallback to empty mappings
            self._category_map = {
                "restaurant": [],
                "cafe": [],
                "bar": [],
                "hotel": [],
                "shopping": [],
                "park": [],
                "entertainment": []
            }

    def matches_filter(self, place_categories: list[dict], filter_type: str) -> bool:
        """
        Check if a place's categories match the filter type using category IDs.

        Args:
            place_categories: List of category dicts from Foursquare API
                             Each dict has: {fsq_category_id, name, short_name, ...}
            filter_type: The filter type (e.g., "restaurant", "cafe", "bar")

        Returns:
            True if the place matches the filter, False otherwise
        """
        if not place_categories:
            return False

        filter_type_lower = filter_type.lower()

        # Get the category IDs for this filter type
        valid_category_ids = set(self._category_map.get(filter_type_lower, []))

        if not valid_category_ids:
            # Fallback to name matching if no category IDs available
            logger.warning(f"No category IDs for filter: {filter_type}")
            return self._fallback_name_matching(place_categories, filter_type)

        # Check if any of the place's category IDs match our filter
        for category in place_categories:
            cat_id = category.get('fsq_category_id')
            if cat_id in valid_category_ids:
                return True

        return False

    def _fallback_name_matching(self, place_categories: list[dict], filter_type: str) -> bool:
        """Fallback to name-based matching if category IDs aren't available."""
        filter_lower = filter_type.lower()

        for category in place_categories:
            cat_name = category.get('name', '').lower()
            if filter_lower in cat_name:
                return True

        return False


# Global instance
category_filter = CategoryFilter()
