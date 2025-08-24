"""
Place Metrics Service
Tracks enrichment metrics, quality scores, and system health
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import logging

from ..models import Place
from ..config import settings

logger = logging.getLogger(__name__)


class PlaceMetricsService:
    """Service for tracking place data metrics and monitoring"""

    def __init__(self):
        self.metrics = {
            'enrichment_success': 0,
            'enrichment_failed': 0,
            'quality_scores': [],
            'search_performance': []
        }
        # Limit in-memory storage to prevent unbounded growth
        self.max_quality_scores = 1000
        self.max_search_performance = 1000

    async def track_enrichment_attempt(self, place_id: int, success: bool, error: Optional[str] = None):
        """Track enrichment attempt"""
        if success:
            self.metrics['enrichment_success'] += 1
            logger.info(f"Enrichment successful for place {place_id}")
        else:
            self.metrics['enrichment_failed'] += 1
            logger.warning(f"Enrichment failed for place {place_id}: {error}")

    async def record_quality_score(self, place_id: int, quality_score: float):
        """Record quality score for a place"""
        self.metrics['quality_scores'].append({
            'place_id': place_id,
            'score': quality_score,
            'timestamp': datetime.now(timezone.utc)
        })
        # Limit list size to prevent unbounded growth
        if len(self.metrics['quality_scores']) > self.max_quality_scores:
            self.metrics['quality_scores'] = self.metrics['quality_scores'][-self.max_quality_scores:]

    async def track_search_performance(self, query_time_ms: float, results_count: int):
        """Track search performance metrics"""
        self.metrics['search_performance'].append({
            'query_time_ms': query_time_ms,
            'results_count': results_count,
            'timestamp': datetime.now(timezone.utc)
        })
        # Limit list size to prevent unbounded growth
        if len(self.metrics['search_performance']) > self.max_search_performance:
            self.metrics['search_performance'] = self.metrics['search_performance'][-self.max_search_performance:]

    async def get_enrichment_stats(self, db: AsyncSession) -> Dict:
        """Get comprehensive enrichment statistics"""
        try:
            # Total places count
            total_result = await db.execute(select(func.count(Place.id)))
            total_places = total_result.scalar_one()

            # Enriched places count
            enriched_result = await db.execute(
                select(func.count(Place.id)).where(
                    Place.last_enriched_at.isnot(None))
            )
            enriched_places = enriched_result.scalar_one()

            # Calculate average quality score using aggregate query
            quality_result = await db.execute(
                select(
                    func.avg(Place.place_metadata['quality_score'].astext.cast(float)))
                .where(Place.place_metadata.isnot(None))
            )
            avg_quality_score = quality_result.scalar_one() or 0

            # Data source distribution
            source_result = await db.execute(
                select(Place.data_source, func.count(Place.id))
                .group_by(Place.data_source)
            )
            source_distribution = dict(source_result.all())

            # TTL compliance using aggregate queries
            now = datetime.now(timezone.utc)

            # Count places with recent enrichment (14 days for hot places, 60 for others)
            hot_cutoff = now - timedelta(days=14)
            cold_cutoff = now - timedelta(days=60)

            ttl_compliant_result = await db.execute(
                select(func.count(Place.id))
                .where(
                    Place.last_enriched_at.isnot(None),
                    or_(
                        and_(
                            Place.place_metadata['is_hot'].astext.cast(
                                bool) == True,
                            Place.last_enriched_at >= hot_cutoff
                        ),
                        and_(
                            or_(
                                Place.place_metadata['is_hot'].astext.cast(
                                    bool) == False,
                                Place.place_metadata['is_hot'].is_(None)
                            ),
                            Place.last_enriched_at >= cold_cutoff
                        )
                    )
                )
            )
            ttl_compliant = ttl_compliant_result.scalar_one() or 0

            ttl_compliance_rate = (
                ttl_compliant / total_places * 100) if total_places > 0 else 0

            # Enrichment success rate
            total_attempts = self.metrics['enrichment_success'] + \
                self.metrics['enrichment_failed']
            enrichment_success_rate = (
                (self.metrics['enrichment_success'] / total_attempts * 100)
                if total_attempts > 0 else 0
            )

            # Average search performance
            if self.metrics['search_performance']:
                avg_query_time = sum(
                    p['query_time_ms'] for p in self.metrics['search_performance']) / len(self.metrics['search_performance'])
            else:
                avg_query_time = 0

            return {
                "total_places": total_places,
                "enriched_places": enriched_places,
                "enrichment_rate": (enriched_places / total_places * 100) if total_places > 0 else 0,
                "average_quality_score": round(avg_quality_score, 3),
                "source_distribution": source_distribution,
                "ttl_compliance_rate": round(ttl_compliance_rate, 2),
                "enrichment_success_rate": round(enrichment_success_rate, 2),
                "average_search_time_ms": round(avg_query_time, 2),
                "enrichment_ttl_hot": 14,
                "enrichment_ttl_cold": 60,
                "max_enrichment_distance": 150,
                "min_name_similarity": 0.65,
                "metrics_timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get enrichment stats: {e}")
            return {
                "error": str(e),
                "total_places": 0,
                "enriched_places": 0,
                "enrichment_rate": 0.0,
                "average_quality_score": 0.0
            }

    def _calculate_quality_score(self, place: Place) -> float:
        """Calculate quality score for place"""
        score = 0.0

        # Phone (+0.3)
        if place.phone:
            score += 0.3

        # Hours (+0.3)
        if hasattr(place, 'place_metadata') and place.place_metadata and isinstance(place.place_metadata, dict) and place.place_metadata.get('opening_hours'):
            score += 0.3

        # Photos (+0.2)
        if hasattr(place, 'place_metadata') and place.place_metadata and isinstance(place.place_metadata, dict) and place.place_metadata.get('photos'):
            score += 0.2

        # Recently enriched (+0.2)
        if place.last_enriched_at:
            days_since_enrichment = (
                datetime.now(timezone.utc) - place.last_enriched_at).days
            if days_since_enrichment < 14:
                score += 0.2

        return min(score, 1.0)

    def _is_hot_place(self, place: Place) -> bool:
        """Determine if place is 'hot' (frequently visited)"""
        return place.rating and place.rating >= 4.0

    async def get_system_health(self) -> Dict:
        """Get system health metrics"""
        return {
            "status": "healthy",
            "enrichment_success_rate": self._get_enrichment_success_rate(),
            "average_search_time_ms": self._get_average_search_time(),
            "total_metrics_recorded": len(self.metrics['quality_scores']),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    def _get_enrichment_success_rate(self) -> float:
        """Calculate enrichment success rate"""
        total = self.metrics['enrichment_success'] + \
            self.metrics['enrichment_failed']
        return (self.metrics['enrichment_success'] / total * 100) if total > 0 else 0

    def _get_average_search_time(self) -> float:
        """Calculate average search time"""
        if not self.metrics['search_performance']:
            return 0
        return sum(p['query_time_ms'] for p in self.metrics['search_performance']) / len(self.metrics['search_performance'])


# Global instance
place_metrics_service = PlaceMetricsService()
