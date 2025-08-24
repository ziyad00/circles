
from fastapi import Depends, HTTPException, status
from ..models import User
from ..services.jwt_service import JWTService

async def get_current_admin_user(current_user: User = Depends(JWTService.get_current_user)) -> User:
    """
    Dependency to get current admin user.
    Raises HTTPException if user is not an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

