"""
Robust place filtering service with comprehensive matching logic.
"""
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class PlaceFilterResult:
    """Result of place filtering with match details."""
    matches: bool
    confidence: float
    matched_criteria: List[str]
    reason: str = ""


class PlaceFilteringService:
    """Robust place filtering service with comprehensive matching logic."""
    
    def __init__(self):
        # Comprehensive place type mappings with synonyms and categories
        self.place_type_mappings = {
            "restaurant": {
                "keywords": ["restaurant", "dining", "eatery", "bistro", "grill", "kitchen", "food"],
                "categories": ["Restaurant", "Food", "Dining", "Eatery", "Bistro", "Grill", "Kitchen"],
                "exclude": ["cafe", "coffee", "bar", "pub", "fast food", "takeaway"]
            },
            "cafe": {
                "keywords": ["cafe", "coffee", "coffeehouse", "coffee shop", "espresso", "latte"],
                "categories": ["Cafe", "Coffee", "Coffeehouse", "Coffee Shop", "Espresso Bar"],
                "exclude": ["restaurant", "bar", "pub", "fast food"]
            },
            "bar": {
                "keywords": ["bar", "pub", "tavern", "lounge", "cocktail", "wine", "beer"],
                "categories": ["Bar", "Pub", "Tavern", "Lounge", "Cocktail Bar", "Wine Bar", "Beer Bar"],
                "exclude": ["restaurant", "cafe", "coffee"]
            },
            "hotel": {
                "keywords": ["hotel", "inn", "lodge", "resort", "accommodation", "hostel"],
                "categories": ["Hotel", "Inn", "Lodge", "Resort", "Accommodation", "Hostel"],
                "exclude": ["restaurant", "cafe", "bar"]
            },
            "shopping": {
                "keywords": ["shop", "store", "mall", "market", "boutique", "retail"],
                "categories": ["Shop", "Store", "Mall", "Market", "Boutique", "Retail"],
                "exclude": ["restaurant", "cafe", "bar"]
            },
            "entertainment": {
                "keywords": ["cinema", "theater", "theatre", "club", "entertainment", "gaming", "arcade"],
                "categories": ["Cinema", "Theater", "Theatre", "Club", "Entertainment", "Gaming", "Arcade"],
                "exclude": ["restaurant", "cafe", "bar"]
            },
            "park": {
                "keywords": ["park", "garden", "playground", "recreation", "outdoor"],
                "categories": ["Park", "Garden", "Playground", "Recreation", "Outdoor"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "museum": {
                "keywords": ["museum", "gallery", "exhibition", "art", "history", "cultural"],
                "categories": ["Museum", "Gallery", "Exhibition", "Art", "History", "Cultural"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "gym": {
                "keywords": ["gym", "fitness", "workout", "exercise", "sports", "training"],
                "categories": ["Gym", "Fitness", "Workout", "Exercise", "Sports", "Training"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "pharmacy": {
                "keywords": ["pharmacy", "drugstore", "chemist", "medical", "health"],
                "categories": ["Pharmacy", "Drugstore", "Chemist", "Medical", "Health"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "gas_station": {
                "keywords": ["gas", "fuel", "petrol", "station", "service"],
                "categories": ["Gas Station", "Fuel", "Petrol", "Service Station"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "bank": {
                "keywords": ["bank", "atm", "financial", "credit", "loan"],
                "categories": ["Bank", "ATM", "Financial", "Credit Union"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "hospital": {
                "keywords": ["hospital", "clinic", "medical", "health", "emergency"],
                "categories": ["Hospital", "Clinic", "Medical", "Health", "Emergency"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "school": {
                "keywords": ["school", "university", "college", "education", "academy"],
                "categories": ["School", "University", "College", "Education", "Academy"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            },
            "church": {
                "keywords": ["church", "mosque", "temple", "religious", "worship", "cathedral"],
                "categories": ["Church", "Mosque", "Temple", "Religious", "Worship", "Cathedral"],
                "exclude": ["restaurant", "cafe", "bar", "shop"]
            }
        }
        
        # Cuisine type mappings
        self.cuisine_mappings = {
            "italian": ["italian", "pizza", "pasta", "risotto", "gelato", "espresso"],
            "chinese": ["chinese", "dim sum", "noodles", "rice", "wok", "szechuan"],
            "japanese": ["japanese", "sushi", "ramen", "tempura", "sashimi", "teriyaki"],
            "mexican": ["mexican", "taco", "burrito", "quesadilla", "enchilada", "guacamole"],
            "indian": ["indian", "curry", "tandoor", "naan", "biryani", "masala"],
            "thai": ["thai", "pad thai", "tom yum", "green curry", "mango sticky rice"],
            "french": ["french", "bistro", "brasserie", "croissant", "baguette", "wine"],
            "american": ["american", "burger", "bbq", "steak", "fries", "hot dog"],
            "mediterranean": ["mediterranean", "greek", "turkish", "hummus", "falafel", "olive"],
            "korean": ["korean", "kimchi", "bulgogi", "bibimbap", "korean bbq"],
            "vietnamese": ["vietnamese", "pho", "banh mi", "spring roll", "noodle soup"],
            "lebanese": ["lebanese", "middle eastern", "shawarma", "kebab", "mezze"],
            "seafood": ["seafood", "fish", "lobster", "crab", "shrimp", "oyster"],
            "vegetarian": ["vegetarian", "vegan", "plant-based", "organic", "healthy"],
            "fast_food": ["fast food", "quick", "takeaway", "delivery", "chain"],
            "dessert": ["dessert", "sweet", "cake", "ice cream", "pastry", "chocolate"]
        }
        
        # Price tier mappings
        self.price_mappings = {
            "$": {"keywords": ["cheap", "budget", "affordable", "inexpensive"], "range": (0, 2)},
            "$$": {"keywords": ["moderate", "mid-range", "reasonable"], "range": (2, 3)},
            "$$$": {"keywords": ["expensive", "upscale", "fine dining", "premium"], "range": (3, 4)},
            "$$$$": {"keywords": ["very expensive", "luxury", "high-end", "exclusive"], "range": (4, 5)}
        }

    def filter_place_type(self, place_type: str, place_data: Dict[str, Any]) -> PlaceFilterResult:
        """
        Robust place type filtering with comprehensive matching.
        
        Args:
            place_type: The requested place type (e.g., "restaurant", "cafe")
            place_data: Place data containing categories, name, etc.
            
        Returns:
            PlaceFilterResult with match details
        """
        if not place_type or not place_data:
            return PlaceFilterResult(matches=True, confidence=1.0, matched_criteria=[])
        
        place_type_lower = place_type.lower().strip()
        
        # Check if place_type is in our mappings
        if place_type_lower not in self.place_type_mappings:
            # Fallback to simple matching for unknown types
            return self._simple_place_type_match(place_type_lower, place_data)
        
        mapping = self.place_type_mappings[place_type_lower]
        matched_criteria = []
        confidence = 0.0
        
        # Get place data
        primary_category = (place_data.get("primary_category") or "").lower()
        categories = (place_data.get("categories") or "").lower()
        name = (place_data.get("name") or "").lower()
        description = (place_data.get("description") or "").lower()
        
        # Check for exclusions first
        for exclude_term in mapping["exclude"]:
            if (exclude_term in primary_category or 
                exclude_term in categories or 
                exclude_term in name or 
                exclude_term in description):
                return PlaceFilterResult(
                    matches=False, 
                    confidence=0.0, 
                    matched_criteria=[],
                    reason=f"Excluded by term: {exclude_term}"
                )
        
        # Check primary category match
        for category in mapping["categories"]:
            if category.lower() in primary_category:
                matched_criteria.append(f"primary_category: {category}")
                confidence += 0.4
                break
        
        # Check categories match
        for category in mapping["categories"]:
            if category.lower() in categories:
                matched_criteria.append(f"categories: {category}")
                confidence += 0.3
                break
        
        # Check keyword matches in name and description
        for keyword in mapping["keywords"]:
            if keyword in name:
                matched_criteria.append(f"name: {keyword}")
                confidence += 0.2
            if keyword in description:
                matched_criteria.append(f"description: {keyword}")
                confidence += 0.1
        
        # Check for partial matches in categories
        categories_list = [cat.strip().lower() for cat in categories.split(',') if cat.strip()]
        for cat in categories_list:
            for keyword in mapping["keywords"]:
                if keyword in cat or cat in keyword:
                    matched_criteria.append(f"category_match: {cat}")
                    confidence += 0.15
        
        # Determine if it's a match (confidence threshold)
        matches = confidence >= 0.3
        
        return PlaceFilterResult(
            matches=matches,
            confidence=min(confidence, 1.0),
            matched_criteria=matched_criteria,
            reason=f"Confidence: {confidence:.2f}" if matches else f"Low confidence: {confidence:.2f}"
        )

    def filter_cuisine(self, cuisine: str, place_data: Dict[str, Any]) -> PlaceFilterResult:
        """
        Robust cuisine filtering.
        
        Args:
            cuisine: The requested cuisine type
            place_data: Place data containing cuisine information
            
        Returns:
            PlaceFilterResult with match details
        """
        if not cuisine or not place_data:
            return PlaceFilterResult(matches=True, confidence=1.0, matched_criteria=[])
        
        cuisine_lower = cuisine.lower().strip()
        
        # Check if cuisine is in our mappings
        if cuisine_lower not in self.cuisine_mappings:
            # Fallback to simple matching
            return self._simple_cuisine_match(cuisine_lower, place_data)
        
        cuisine_keywords = self.cuisine_mappings[cuisine_lower]
        matched_criteria = []
        confidence = 0.0
        
        # Get place data
        primary_category = (place_data.get("primary_category") or "").lower()
        categories = (place_data.get("categories") or "").lower()
        name = (place_data.get("name") or "").lower()
        description = (place_data.get("description") or "").lower()
        
        # Check for cuisine keywords
        for keyword in cuisine_keywords:
            if keyword in primary_category:
                matched_criteria.append(f"primary_category: {keyword}")
                confidence += 0.3
            if keyword in categories:
                matched_criteria.append(f"categories: {keyword}")
                confidence += 0.25
            if keyword in name:
                matched_criteria.append(f"name: {keyword}")
                confidence += 0.2
            if keyword in description:
                matched_criteria.append(f"description: {keyword}")
                confidence += 0.15
        
        matches = confidence >= 0.2
        
        return PlaceFilterResult(
            matches=matches,
            confidence=min(confidence, 1.0),
            matched_criteria=matched_criteria,
            reason=f"Cuisine confidence: {confidence:.2f}" if matches else f"Low cuisine confidence: {confidence:.2f}"
        )

    def filter_price(self, price_budget: str, place_data: Dict[str, Any]) -> PlaceFilterResult:
        """
        Robust price filtering.
        
        Args:
            price_budget: The requested price tier ($, $$, $$$, $$$$)
            place_data: Place data containing price information
            
        Returns:
            PlaceFilterResult with match details
        """
        if not price_budget or not place_data:
            return PlaceFilterResult(matches=True, confidence=1.0, matched_criteria=[])
        
        price_budget = price_budget.strip()
        
        if price_budget not in self.price_mappings:
            return PlaceFilterResult(matches=True, confidence=1.0, matched_criteria=[])
        
        mapping = self.price_mappings[price_budget]
        matched_criteria = []
        confidence = 0.0
        
        # Get place data
        price_tier = place_data.get("price_tier", 0)
        primary_category = (place_data.get("primary_category") or "").lower()
        categories = (place_data.get("categories") or "").lower()
        name = (place_data.get("name") or "").lower()
        description = (place_data.get("description") or "").lower()
        
        # Check price tier range
        min_price, max_price = mapping["range"]
        if min_price <= price_tier <= max_price:
            matched_criteria.append(f"price_tier: {price_tier}")
            confidence += 0.5
        
        # Check for price keywords
        for keyword in mapping["keywords"]:
            if keyword in primary_category:
                matched_criteria.append(f"primary_category: {keyword}")
                confidence += 0.2
            if keyword in categories:
                matched_criteria.append(f"categories: {keyword}")
                confidence += 0.15
            if keyword in name:
                matched_criteria.append(f"name: {keyword}")
                confidence += 0.1
            if keyword in description:
                matched_criteria.append(f"description: {keyword}")
                confidence += 0.05
        
        matches = confidence >= 0.3
        
        return PlaceFilterResult(
            matches=matches,
            confidence=min(confidence, 1.0),
            matched_criteria=matched_criteria,
            reason=f"Price confidence: {confidence:.2f}" if matches else f"Low price confidence: {confidence:.2f}"
        )

    def filter_location(self, country: str = None, city: str = None, neighborhood: str = None, 
                       place_data: Dict[str, Any] = None) -> PlaceFilterResult:
        """
        Robust location filtering.
        
        Args:
            country: Country filter
            city: City filter  
            neighborhood: Neighborhood filter
            place_data: Place data containing location information
            
        Returns:
            PlaceFilterResult with match details
        """
        if not place_data:
            return PlaceFilterResult(matches=True, confidence=1.0, matched_criteria=[])
        
        matched_criteria = []
        confidence = 0.0
        
        # Get place location data
        place_country = (place_data.get("country") or "").lower()
        place_city = (place_data.get("city") or "").lower()
        place_neighborhood = (place_data.get("neighborhood") or "").lower()
        
        # Check country match
        if country:
            country_lower = country.lower().strip()
            if country_lower in place_country or place_country in country_lower:
                matched_criteria.append(f"country: {country}")
                confidence += 0.4
        
        # Check city match
        if city:
            city_lower = city.lower().strip()
            if city_lower in place_city or place_city in city_lower:
                matched_criteria.append(f"city: {city}")
                confidence += 0.3
        
        # Check neighborhood match
        if neighborhood:
            neighborhood_lower = neighborhood.lower().strip()
            if neighborhood_lower in place_neighborhood or place_neighborhood in neighborhood_lower:
                matched_criteria.append(f"neighborhood: {neighborhood}")
                confidence += 0.3
        
        # If no location filters provided, it's a match
        if not any([country, city, neighborhood]):
            matches = True
            confidence = 1.0
        else:
            # Need at least one location match
            matches = confidence >= 0.3
        
        return PlaceFilterResult(
            matches=matches,
            confidence=min(confidence, 1.0),
            matched_criteria=matched_criteria,
            reason=f"Location confidence: {confidence:.2f}" if matches else f"Low location confidence: {confidence:.2f}"
        )

    def _simple_place_type_match(self, place_type: str, place_data: Dict[str, Any]) -> PlaceFilterResult:
        """Fallback simple matching for unknown place types."""
        primary_category = (place_data.get("primary_category") or "").lower()
        categories = (place_data.get("categories") or "").lower()
        name = (place_data.get("name") or "").lower()
        
        matched_criteria = []
        confidence = 0.0
        
        if place_type in primary_category:
            matched_criteria.append(f"primary_category: {place_type}")
            confidence += 0.4
        if place_type in categories:
            matched_criteria.append(f"categories: {place_type}")
            confidence += 0.3
        if place_type in name:
            matched_criteria.append(f"name: {place_type}")
            confidence += 0.2
        
        matches = confidence >= 0.3
        
        return PlaceFilterResult(
            matches=matches,
            confidence=min(confidence, 1.0),
            matched_criteria=matched_criteria,
            reason=f"Simple match confidence: {confidence:.2f}" if matches else f"Low simple match confidence: {confidence:.2f}"
        )

    def _simple_cuisine_match(self, cuisine: str, place_data: Dict[str, Any]) -> PlaceFilterResult:
        """Fallback simple matching for unknown cuisines."""
        primary_category = (place_data.get("primary_category") or "").lower()
        categories = (place_data.get("categories") or "").lower()
        name = (place_data.get("name") or "").lower()
        
        matched_criteria = []
        confidence = 0.0
        
        if cuisine in primary_category:
            matched_criteria.append(f"primary_category: {cuisine}")
            confidence += 0.3
        if cuisine in categories:
            matched_criteria.append(f"categories: {cuisine}")
            confidence += 0.25
        if cuisine in name:
            matched_criteria.append(f"name: {cuisine}")
            confidence += 0.2
        
        matches = confidence >= 0.2
        
        return PlaceFilterResult(
            matches=matches,
            confidence=min(confidence, 1.0),
            matched_criteria=matched_criteria,
            reason=f"Simple cuisine confidence: {confidence:.2f}" if matches else f"Low simple cuisine confidence: {confidence:.2f}"
        )

    def apply_all_filters(self, place_data: Dict[str, Any], place_type: str = None, 
                         cuisine: str = None, price_budget: str = None,
                         country: str = None, city: str = None, neighborhood: str = None) -> PlaceFilterResult:
        """
        Apply all filters and return combined result.
        
        Args:
            place_data: Place data to filter
            place_type: Place type filter
            cuisine: Cuisine filter
            price_budget: Price budget filter
            country: Country filter
            city: City filter
            neighborhood: Neighborhood filter
            
        Returns:
            PlaceFilterResult with overall match status
        """
        all_results = []
        all_matched_criteria = []
        total_confidence = 0.0
        filter_count = 0
        
        # Apply place type filter
        if place_type:
            result = self.filter_place_type(place_type, place_data)
            all_results.append(result)
            all_matched_criteria.extend(result.matched_criteria)
            total_confidence += result.confidence
            filter_count += 1
        
        # Apply cuisine filter
        if cuisine:
            result = self.filter_cuisine(cuisine, place_data)
            all_results.append(result)
            all_matched_criteria.extend(result.matched_criteria)
            total_confidence += result.confidence
            filter_count += 1
        
        # Apply price filter
        if price_budget:
            result = self.filter_price(price_budget, place_data)
            all_results.append(result)
            all_matched_criteria.extend(result.matched_criteria)
            total_confidence += result.confidence
            filter_count += 1
        
        # Apply location filters
        if any([country, city, neighborhood]):
            result = self.filter_location(country, city, neighborhood, place_data)
            all_results.append(result)
            all_matched_criteria.extend(result.matched_criteria)
            total_confidence += result.confidence
            filter_count += 1
        
        # If no filters applied, it's a match
        if filter_count == 0:
            return PlaceFilterResult(matches=True, confidence=1.0, matched_criteria=[])
        
        # All filters must pass
        all_match = all(result.matches for result in all_results)
        avg_confidence = total_confidence / filter_count if filter_count > 0 else 0.0
        
        return PlaceFilterResult(
            matches=all_match,
            confidence=avg_confidence,
            matched_criteria=all_matched_criteria,
            reason=f"All filters passed: {filter_count} filters, avg confidence: {avg_confidence:.2f}" if all_match else "One or more filters failed"
        )


# Global instance
place_filtering_service = PlaceFilteringService()
