import uuid

from fastapi import APIRouter, Depends, Query, Request

from snapland.api.deps import get_area_service, get_rate_limiter
from snapland.api.v1.auth import get_current_user_id
from snapland.core.domain.area import Area, CreateAreaRequest, UpdateAreaRequest
from snapland.core.interfaces.repositories import AreaPage
from snapland.core.interfaces.services import IAreaService, IRateLimiter
from snapland.middleware.rate_limiter import check_rate_limit

router = APIRouter(prefix="/areas", tags=["areas"])

@router.get("", response_model=AreaPage)
async def get_areas(
    request: Request,
    bounds: str = Query(..., description="minLng,minLat,maxLng,maxLat"),
    zoom: int | None = Query(None),
    limit: int = Query(500),
    user_id: uuid.UUID = Depends(get_current_user_id),
    area_svc=Depends(get_area_service),
    limiter=Depends(get_rate_limiter),
):
    from snapland.middleware.rate_limiter import check_rate_limit
    await check_rate_limit(limiter, str(user_id), "http", 100, 60)
    
    try:
        parts = [float(x) for x in bounds.split(",")]
        if len(parts) != 4:
            raise ValueError()
        min_lng, min_lat, max_lng, max_lat = parts
    except ValueError:
        from snapland.core.domain.exceptions import ValidationError
        raise ValidationError("Invalid bounds format. Expected minLng,minLat,maxLng,maxLat")
        
    return await area_svc.get_areas_in_bounds(min_lng, min_lat, max_lng, max_lat, zoom=zoom, limit=limit)

@router.post("", response_model=Area)
async def create_area(
    req: CreateAreaRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    area_svc: IAreaService = Depends(get_area_service),
    limiter: IRateLimiter = Depends(get_rate_limiter)
):
    await check_rate_limit(limiter, str(user_id), "draw_action", 50, 60)
    return await area_svc.create_area(req, user_id)

@router.get("/{area_id}", response_model=Area)
async def get_area(
    area_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    area_svc: IAreaService = Depends(get_area_service)
):
    return await area_svc.get_area(area_id)

# Explicit design decision: Any authenticated user can edit any area (collaborative).
# No ownership check is applied here.
@router.put("/{area_id}", response_model=Area)
async def update_area(
    area_id: uuid.UUID,
    req: UpdateAreaRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    area_svc: IAreaService = Depends(get_area_service),
    limiter: IRateLimiter = Depends(get_rate_limiter)
):
    await check_rate_limit(limiter, str(user_id), "draw_action", 50, 60)
    return await area_svc.update_area(area_id, req, user_id)

# Explicit design decision: Any authenticated user can delete any area (collaborative).
# No ownership check is applied here.
@router.delete("/{area_id}")
async def delete_area(
    area_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    area_svc: IAreaService = Depends(get_area_service),
    limiter: IRateLimiter = Depends(get_rate_limiter)
):
    await check_rate_limit(limiter, str(user_id), "draw_action", 50, 60)
    await area_svc.delete_area(area_id, user_id)
    return {"status": "ok"}

@router.get("/{area_id}/history")
async def get_history(
    area_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    area_svc: IAreaService = Depends(get_area_service)
):
    history = await area_svc.get_history(area_id)
    return history
