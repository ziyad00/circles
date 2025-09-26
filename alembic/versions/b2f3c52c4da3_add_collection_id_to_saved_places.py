"""Add collection_id to saved_places and backfill

Revision ID: b2f3c52c4da3
Revises: c9fd549d5f23
Create Date: 2024-03-15 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b2f3c52c4da3"
down_revision = "c9fd549d5f23"
branch_labels = None
depends_on = None


def _normalize_name(name: str | None) -> str:
    if not name:
        return "Favorites"
    trimmed = name.strip()
    return trimmed or "Favorites"


def upgrade() -> None:
    op.add_column(
        "saved_places",
        sa.Column("collection_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_saved_places_collection_id",
        "saved_places",
        "user_collections",
        ["collection_id"],
        ["id"],
        ondelete="CASCADE",
    )

    conn = op.get_bind()
    metadata = sa.MetaData()
    metadata.reflect(
        bind=conn,
        only={"saved_places", "user_collections", "user_collection_places"},
    )

    saved_places = metadata.tables["saved_places"]
    user_collections = metadata.tables["user_collections"]
    user_collection_places = metadata.tables["user_collection_places"]

    saved_rows = conn.execute(
        sa.select(
            saved_places.c.id,
            saved_places.c.user_id,
            saved_places.c.place_id,
            saved_places.c.list_name,
            saved_places.c.created_at,
        ).order_by(
            saved_places.c.created_at.desc().nullslast(),
            saved_places.c.id.desc(),
        )
    ).fetchall()

    seen_pairs: dict[tuple[int, int], int] = {}

    for row in saved_rows:
        normalized_name = _normalize_name(row.list_name)

        collection_id = conn.execute(
            sa.select(user_collections.c.id).where(
                sa.and_(
                    user_collections.c.user_id == row.user_id,
                    user_collections.c.name == normalized_name,
                )
            )
        ).scalar()

        if collection_id is None:
            insert_result = conn.execute(
                user_collections.insert().values(
                    user_id=row.user_id,
                    name=normalized_name,
                    description=None,
                    is_public=True,
                    visibility="public",
                    created_at=row.created_at or sa.func.now(),
                )
            )
            collection_id = insert_result.inserted_primary_key[0]

        pair = (row.user_id, row.place_id)
        if pair in seen_pairs:
            # Remove duplicate saved place and its association for this collection
            conn.execute(
                user_collection_places.delete().where(
                    sa.and_(
                        user_collection_places.c.collection_id == collection_id,
                        user_collection_places.c.place_id == row.place_id,
                    )
                )
            )
            conn.execute(
                saved_places.delete().where(saved_places.c.id == row.id)
            )
            continue

        conn.execute(
            saved_places.update()
            .where(saved_places.c.id == row.id)
            .values(
                collection_id=collection_id,
                list_name=normalized_name,
            )
        )

        existing_link = conn.execute(
            sa.select(user_collection_places.c.id).where(
                sa.and_(
                    user_collection_places.c.collection_id == collection_id,
                    user_collection_places.c.place_id == row.place_id,
                )
            )
        ).scalar()
        if existing_link is None:
            conn.execute(
                user_collection_places.insert().values(
                    collection_id=collection_id,
                    place_id=row.place_id,
                    added_at=row.created_at or sa.func.now(),
                )
            )

        seen_pairs[pair] = collection_id

    op.alter_column(
        "saved_places",
        "collection_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_saved_place_user_place", "saved_places", ["user_id", "place_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_saved_place_user_place", "saved_places", type_="unique")
    op.drop_constraint("fk_saved_places_collection_id", "saved_places", type_="foreignkey")
    op.drop_column("saved_places", "collection_id")
