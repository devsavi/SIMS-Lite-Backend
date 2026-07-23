"""
Admin notification endpoints — Phase 6A.

Routes:
    POST /admin/notifications/send   — send targeted/broadcast notification
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_roles
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import SuccessResponse
from app.schemas.notification import AdminNotificationSend, NotificationRead
from app.services.notification import NotificationService

router = APIRouter()


@router.post(
    "/send",
    response_model=SuccessResponse[NotificationRead],
    summary="Send admin notification",
    description=(
        "Admin-only. Send a notification to an individual user, a role group "
        "(ADMIN / OFFICER / STORE_KEEPER), or broadcast to everyone.\n\n"
        "Provide exactly one of: `recipient_user_id`, `recipient_role`, or `broadcast_all: true`."
    ),
)
async def admin_send_notification(
    payload: AdminNotificationSend,
    current_user: User = Depends(require_roles("ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[NotificationRead]:
    svc = NotificationService(db)
    notification = await svc.admin_send(payload, actor=current_user)
    return SuccessResponse(data=NotificationRead.model_validate(notification))
