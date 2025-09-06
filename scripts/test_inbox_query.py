import asyncio
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.sql import expression as sql_expr

from app.database import AsyncSessionLocal
from app.models import User, DMThread, DMMessage, DMParticipantState


async def run(user_id: int):
    async with AsyncSessionLocal() as db:
        # other user id case expression
        other_user_id = sql_expr.case(
            (DMThread.user_a_id == user_id, DMThread.user_b_id),
            else_=DMThread.user_a_id,
        )

        # last message subquery (decoupled)
        last_msg_ranked = (
            select(
                DMMessage.thread_id,
                DMMessage.text.label("last_message_text"),
                DMMessage.reply_to_text.label("reply_preview"),
                DMMessage.created_at.label("last_message_time"),
                func.row_number().over(
                    partition_by=DMMessage.thread_id,
                    order_by=DMMessage.created_at.desc(),
                ).label("rn"),
            )
            .where(DMMessage.deleted_at.is_(None))
            .subquery()
        )
        last_msg_subq = select(last_msg_ranked).where(
            last_msg_ranked.c.rn == 1).subquery()

        base = (
            select(
                DMThread,
                User.name.label("other_user_name"),
                User.username.label("other_user_username"),
                User.avatar_url.label("other_user_avatar"),
                last_msg_subq.c.last_message_text.label("last_message"),
                last_msg_subq.c.last_message_time.label("last_message_time"),
                last_msg_subq.c.reply_preview.label("reply_preview"),
            )
            .join(
                DMParticipantState,
                and_(
                    DMParticipantState.thread_id == DMThread.id,
                    DMParticipantState.user_id == user_id,
                ),
                isouter=True,
            )
            .join(User, User.id == other_user_id, isouter=True)
            .join(
                last_msg_subq,
                and_(last_msg_subq.c.thread_id == DMThread.id),
                isouter=True,
            )
            .where(
                DMThread.status == "accepted",
                or_(DMThread.user_a_id == user_id,
                    DMThread.user_b_id == user_id),
            )
        )

        total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        print("TOTAL:", total)
        stmt = base.order_by(func.coalesce(
            DMParticipantState.pinned, False).desc(), desc(DMThread.updated_at)).limit(10)
        rows = (await db.execute(stmt)).all()
        print("ROWS:", rows)


if __name__ == "__main__":
    asyncio.run(run(user_id=1))
