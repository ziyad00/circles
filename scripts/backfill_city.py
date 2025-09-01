import asyncio
from sqlalchemy import select, update
from app.database import AsyncSessionLocal
from app.models import Place


async def backfill_riyadh_city() -> int:
    async with AsyncSessionLocal() as session:
        # Update rows with null/empty city within Riyadh bounding box
        stmt = (
            update(Place)
            .where(
                (Place.city.is_(None) | (Place.city == ""))
                & (Place.latitude.isnot(None))
                & (Place.longitude.isnot(None))
                & (Place.latitude.between(24.3, 25.2))
                & (Place.longitude.between(46.2, 47.3))
            )
            .values(city="Riyadh")
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


async def main():
    updated = await backfill_riyadh_city()
    print(f"Backfilled city='Riyadh' for {updated} places")


if __name__ == "__main__":
    asyncio.run(main())
