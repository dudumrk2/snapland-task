
from main import censor_and_normalize


def test_log_redaction_sensitive_keys():
    event_dict = {
        "event": "User logged in",
        "password": "SuperSecretPassword123!",
        "access_token": "eyJhG...",
        "ticket": "ticket-uuid-secret",
        "cookie": "session=abc",
        "authorization": "Bearer xyz",
        "email": "user@example.com",
        "display_name": "Test User",
        "user_id": "12345",
        "safe_key": "safe_value",
    }

    result = censor_and_normalize(None, "info", event_dict)

    assert result["message"] == "User logged in"
    assert "event" not in result
    assert result["password"] == "[REDACTED]"
    assert result["access_token"] == "[REDACTED]"
    assert result["ticket"] == "[REDACTED]"
    assert result["cookie"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert result["email"] == "[REDACTED]"
    assert result["display_name"] == "[REDACTED]"
    # Ensure IDs and safe keys are preserved
    assert result["user_id"] == "12345"
    assert result["safe_key"] == "safe_value"
    assert "instance_id" in result
