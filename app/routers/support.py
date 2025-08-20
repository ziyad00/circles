from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..services.jwt_service import JWTService
from ..models import SupportTicket, User
from ..schemas import SupportTicketCreate, SupportTicketResponse


router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=SupportTicketResponse)
async def create_ticket(
    payload: SupportTicketCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = SupportTicket(user_id=current_user.id, subject=payload.subject, body=payload.body)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@router.get("/tickets", response_model=list[SupportTicketResponse])
async def list_my_tickets(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    res = await db.execute(
        select(SupportTicket).where(SupportTicket.user_id == current_user.id).order_by(SupportTicket.created_at.desc()).offset(offset).limit(limit)
    )
    return res.scalars().all()


