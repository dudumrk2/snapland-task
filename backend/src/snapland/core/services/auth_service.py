import datetime
import hashlib
import secrets
import uuid

import bcrypt
import jwt

from snapland.core.domain.exceptions import AuthError
from snapland.core.domain.user import Session, TokenResponse, User
from snapland.core.interfaces.cache import ICacheRepository
from snapland.core.interfaces.repositories import ISessionRepository, IUserRepository
from snapland.core.interfaces.services import IAuthService


class AuthService(IAuthService):
    def __init__(
        self,
        user_repo: IUserRepository,
        session_repo: ISessionRepository,
        cache_repo: ICacheRepository,
        jwt_private_key: str = "secret",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7
    ) -> None:
        self.user_repo = user_repo
        self.session_repo = session_repo
        self.cache_repo = cache_repo
        self.jwt_private_key = jwt_private_key
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def register(self, email: str, password: str, display_name: str) -> User:
        pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        # Create user (password hash might be handled outside or added to User model)
        user = User(id=uuid.uuid4(), email=email, display_name=display_name, password_hash=pwd_hash)
        # Note: if User gets updated with password_hash, we'd pass it here
        user = await self.user_repo.create(user)
        return user

    async def login(self, email: str, password: str, ip_address: str = "0.0.0.0") -> TokenResponse:
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise AuthError("Invalid credentials")
        
        if not user.password_hash or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            raise AuthError("Invalid credentials")
        
        access_token = self._create_access_token(user.id)
        refresh_token = secrets.token_urlsafe(32)
        
        session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            family_id=uuid.uuid4(),
            refresh_token_hash=self._hash_token(refresh_token),
            expires_at=(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=self.refresh_token_expire_days)),
            revoked_at=None,
            ip_address=ip_address,
            created_at=datetime.datetime.now(datetime.UTC)
        )
        await self.session_repo.create(session)
        
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh_token(self, refresh_token: str, ip_address: str = "0.0.0.0") -> TokenResponse:
        token_hash = self._hash_token(refresh_token)
        session = await self.session_repo.get_by_token_hash(token_hash)
        
        if not session:
            raise AuthError("Invalid or expired refresh token")
            
        if session.revoked_at:
            await self.session_repo.revoke_family(session.family_id)
            raise AuthError("Token reused, family revoked")
            
        # Rotate token
        await self.session_repo.revoke(session.id)
        
        new_refresh = secrets.token_urlsafe(32)
        new_session = Session(
            id=uuid.uuid4(),
            user_id=session.user_id,
            family_id=session.family_id,
            refresh_token_hash=self._hash_token(new_refresh),
            expires_at=(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=self.refresh_token_expire_days)),
            revoked_at=None,
            ip_address=ip_address,
            created_at=datetime.datetime.now(datetime.UTC)
        )
        await self.session_repo.create(new_session)
        
        new_access = self._create_access_token(session.user_id)
        return TokenResponse(access_token=new_access, refresh_token=new_refresh)

    async def revoke_token(self, refresh_token: str) -> None:
        token_hash = self._hash_token(refresh_token)
        session = await self.session_repo.get_by_token_hash(token_hash)
        if session:
            await self.session_repo.revoke(session.id)

    async def issue_ws_ticket(self, user_id: uuid.UUID) -> str:
        ticket = secrets.token_urlsafe(16)
        key = f"ws_ticket:{ticket}"
        await self.cache_repo.set(key, str(user_id), 30)
        return ticket

    async def redeem_ws_ticket(self, ticket: str) -> uuid.UUID | None:
        key = f"ws_ticket:{ticket}"
        user_id_str = await self.cache_repo.getdel(key)
        if not user_id_str:
            return None
        return uuid.UUID(user_id_str)

    def _create_access_token(self, user_id: uuid.UUID) -> str:
        expire = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=self.access_token_expire_minutes)
        to_encode = {"sub": str(user_id), "exp": expire}
        encoded_jwt = jwt.encode(to_encode, self.jwt_private_key, algorithm="RS256")
        return encoded_jwt

    def verify_access_token(self, token: str, public_key: str) -> uuid.UUID:
        try:
            payload = jwt.decode(token, public_key, algorithms=["RS256"])
            return uuid.UUID(payload["sub"])
        except jwt.PyJWTError:
            raise AuthError("Invalid or expired token")
