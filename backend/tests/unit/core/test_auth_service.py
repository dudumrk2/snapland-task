import pytest
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock
from snapland.core.services.auth_service import AuthService
from snapland.core.domain.user import User, Session

@pytest.fixture
def mock_user_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_email = AsyncMock()
    return repo

@pytest.fixture
def mock_session_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_token_hash = AsyncMock()
    repo.revoke = AsyncMock()
    repo.revoke_family = AsyncMock()
    return repo

@pytest.fixture
def mock_cache_repo():
    repo = MagicMock()
    repo.set = AsyncMock()
    repo.get = AsyncMock()
    return repo

@pytest.fixture
def auth_service(mock_user_repo, mock_session_repo, mock_cache_repo):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()).decode()
    return AuthService(
        user_repo=mock_user_repo,
        session_repo=mock_session_repo,
        cache_repo=mock_cache_repo,
        jwt_private_key=private_key
    )

@pytest.mark.asyncio
async def test_register(auth_service, mock_user_repo):
    test_user = User(id=uuid.uuid4(), email="test@test.com", display_name="Test")
    mock_user_repo.create.return_value = test_user
    
    user = await auth_service.register("test@test.com", "password123", "Test")
    
    assert user.email == "test@test.com"
    assert user.display_name == "Test"
    mock_user_repo.create.assert_called_once()

@pytest.mark.asyncio
async def test_login_success(auth_service, mock_user_repo, mock_session_repo):
    test_user = User(id=uuid.uuid4(), email="test@test.com", display_name="Test")
    mock_user_repo.get_by_email.return_value = test_user
    
    result = await auth_service.login("test@test.com", "password123")
    
    assert result.access_token is not None
    assert result.refresh_token is not None
    mock_session_repo.create.assert_called_once()

@pytest.mark.asyncio
async def test_login_invalid_credentials(auth_service, mock_user_repo):
    mock_user_repo.get_by_email.return_value = None
    
    with pytest.raises(Exception, match="Invalid credentials"):
        await auth_service.login("wrong@test.com", "password123")

@pytest.mark.asyncio
async def test_refresh_token_success(auth_service, mock_session_repo):
    session = Session(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        refresh_token_hash="hash",
        expires_at=datetime.datetime.now(datetime.UTC),
        revoked_at=None,
        ip_address="0.0.0.0",
        created_at=datetime.datetime.now(datetime.UTC)
    )
    mock_session_repo.get_by_token_hash.return_value = session
    
    result = await auth_service.refresh_token("valid_token")
    
    assert result.access_token is not None
    assert result.refresh_token is not None
    mock_session_repo.revoke.assert_called_once_with(session.id)
    mock_session_repo.create.assert_called_once()

@pytest.mark.asyncio
async def test_refresh_token_revoked(auth_service, mock_session_repo):
    session = Session(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        refresh_token_hash="hash",
        expires_at=datetime.datetime.now(datetime.UTC),
        revoked_at=datetime.datetime.now(datetime.UTC),
        ip_address="0.0.0.0",
        created_at=datetime.datetime.now(datetime.UTC)
    )
    mock_session_repo.get_by_token_hash.return_value = session
    
    with pytest.raises(Exception, match="Token reused, family revoked"):
        await auth_service.refresh_token("revoked_token")
        
    mock_session_repo.revoke_family.assert_called_once_with(session.family_id)

@pytest.mark.asyncio
async def test_revoke_token(auth_service, mock_session_repo):
    session = Session(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        refresh_token_hash="hash",
        expires_at=datetime.datetime.now(datetime.UTC),
        revoked_at=None,
        ip_address="0.0.0.0",
        created_at=datetime.datetime.now(datetime.UTC)
    )
    mock_session_repo.get_by_token_hash.return_value = session
    
    await auth_service.revoke_token("valid_token")
    
    mock_session_repo.revoke.assert_called_once_with(session.id)

@pytest.mark.asyncio
async def test_issue_ws_ticket(auth_service, mock_cache_repo):
    user_id = uuid.uuid4()
    ticket = await auth_service.issue_ws_ticket(user_id)
    
    assert ticket is not None
    mock_cache_repo.set.assert_called_once()
    assert mock_cache_repo.set.call_args[0][0] == f"ws_ticket:{ticket}"

@pytest.mark.asyncio
async def test_redeem_ws_ticket(auth_service, mock_cache_repo):
    user_id = uuid.uuid4()
    mock_cache_repo.get.return_value = str(user_id)
    
    result = await auth_service.redeem_ws_ticket("valid_ticket")
    
    assert result == user_id
    mock_cache_repo.get.assert_called_once_with("ws_ticket:valid_ticket")
