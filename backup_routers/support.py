from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..services.jwt_service import JWTService
from ..models import SupportTicket, User
from ..schemas import SupportTicketCreate, SupportTicketResponse


router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=SupportTicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: SupportTicketCreate,
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Map schema 'body' to model 'message', ensure default status
    t = SupportTicket(
        user_id=current_user.id,
        subject=payload.subject,
        message=payload.body,
        status="open",
    )
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
        select(SupportTicket).where(SupportTicket.user_id == current_user.id).order_by(
            SupportTicket.created_at.desc()).offset(offset).limit(limit)
    )
    return res.scalars().all()


def _require_admin(user: User):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")


@router.get("/admin/tickets", response_model=list[SupportTicketResponse])
async def admin_list_tickets(
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _require_admin(current_user)
    res = await db.execute(
        select(SupportTicket).order_by(
            SupportTicket.created_at.desc()).offset(offset).limit(limit)
    )
    return res.scalars().all()


@router.put("/admin/tickets/{ticket_id}", response_model=SupportTicketResponse)
async def admin_update_ticket(
    ticket_id: int,
    status: str = Query(..., pattern="^(open|closed)$"),
    current_user: User = Depends(JWTService.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    t = res.scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    t.status = status
    await db.commit()
    await db.refresh(t)
    return t
