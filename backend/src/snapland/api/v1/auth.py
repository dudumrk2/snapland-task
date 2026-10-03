import uuid

from fastapi import APIRouter, Cookie, Depends, Request, Response

from snapland.api.deps import get_auth_service, get_rate_limiter
from snapland.core.domain.exceptions import AuthError
from snapland.core.domain.user import LoginRequest, RegisterRequest, TokenResponse, User
from snapland.core.interfaces.services import IAuthService, IRateLimiter
from snapland.middleware.rate_limiter import check_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

def get_client_ip(request: Request) -> str:
    # Basic IP extraction
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0]
    return request.client.host if request.client else "127.0.0.1"

async def get_current_user_id(request: Request, auth_svc: IAuthService = Depends(get_auth_service)) -> uuid.UUID:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise AuthError("Missing or invalid token")
    token = auth.split(" ")[1]
    from snapland.config import settings
    try:
        user_id = auth_svc.verify_access_token(token, settings.JWT_PUBLIC_KEY)
        import structlog
        structlog.contextvars.bind_contextvars(user_id=str(user_id))
        return user_id
    except Exception:
        raise AuthError("Token not verified")

@router.post("/register", response_model=User)
async def register(
    req: RegisterRequest,
    request: Request,
    auth_svc: IAuthService = Depends(get_auth_service),
    limiter: IRateLimiter = Depends(get_rate_limiter)
):
    ip = get_client_ip(request)
    await check_rate_limit(limiter, ip, "auth_register", 20, 60)
    user = await auth_svc.register(req.email, req.password, req.display_name)
    return user

@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    auth_svc: IAuthService = Depends(get_auth_service),
    limiter: IRateLimiter = Depends(get_rate_limiter)
):
    ip = get_client_ip(request)
    await check_rate_limit(limiter, ip, "auth_login", 20, 60)
    
    tokens = await auth_svc.login(req.email, req.password, ip)
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth"
    )
    return tokens

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str = Cookie(None),
    auth_svc: IAuthService = Depends(get_auth_service)
):
    if not refresh_token:
        raise AuthError("No refresh token provided")
    
    ip = get_client_ip(request)
    tokens = await auth_svc.refresh_token(refresh_token, ip)
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth"
    )
    return tokens

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    refresh_token: str = Cookie(None),
    auth_svc: IAuthService = Depends(get_auth_service)
):
    user_id = None
    if refresh_token:
        # Try to resolve user_id from the access token first (fastest path).
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from snapland.config import settings
                user_id = auth_svc.verify_access_token(auth_header.split(" ")[1], settings.JWT_PUBLIC_KEY)
            except Exception:
                pass

        revoked_user_id = await auth_svc.revoke_token(refresh_token)
        if not user_id:
            user_id = revoked_user_id

        # Disconnect on THIS instance immediately.
        if user_id:
            ws_manager = getattr(request.app.state, "ws_manager", None)
            if ws_manager:
                await ws_manager.disconnect_user(user_id)

        # Broadcast logout to ALL instances via Redis control channel.
        if user_id:
            ephemeral_bus = getattr(request.app.state, "ephemeral_bus", None)
            if ephemeral_bus and hasattr(ephemeral_bus, "publish_control"):
                try:
                    await ephemeral_bus.publish_control({"type": "logout", "userId": str(user_id)})
                except Exception:
                    pass  # Best-effort; local disconnect already done above

    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return {"status": "ok"}

@router.post("/ws-ticket")
async def ws_ticket(
    user_id: uuid.UUID = Depends(get_current_user_id),
    auth_svc: IAuthService = Depends(get_auth_service)
):
    ticket = await auth_svc.issue_ws_ticket(user_id)
    return {"ticket": ticket}
