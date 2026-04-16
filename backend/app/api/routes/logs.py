"""Activity log endpoints."""

from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import ActivityServiceDep, CurrentUser
from app.models.activity_log import ActivityAction
from app.schemas.activity_log import ActivityLogResponse

router = APIRouter()


@router.get(
    "",
    response_model=list[ActivityLogResponse],
    summary="List activity logs",
    description=(
        "Return activity log entries for the current user, ordered by most "
        "recent first. Supports filtering by action type, resource, and date range."
    ),
    responses={401: {"description": "Not authenticated"}},
)
async def list_logs(
    current_user: CurrentUser,
    activity: ActivityServiceDep,
    action: ActivityAction | None = Query(None, description="Filter by action type"),
    resource_type: str | None = Query(
        None, description="Filter by resource type (document, job, etc.)"
    ),
    date_from: datetime | None = Query(None, description="After this timestamp"),
    date_to: datetime | None = Query(None, description="Before this timestamp"),
    limit: int = Query(50, ge=1, le=200, description="Maximum entries to return"),
    offset: int = Query(0, ge=0, description="Entries to skip"),
) -> list[ActivityLogResponse]:
    logs = await activity.list_logs(
        actor_id=current_user.id,
        action=action,
        resource_type=resource_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [ActivityLogResponse.model_validate(log) for log in logs]
