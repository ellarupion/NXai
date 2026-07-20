import uuid

import jwt
import pytest
from fastapi import HTTPException

from interfaces.api.auth import JWT_ALGORITHM, _decode_access_token, create_access_token


def test_create_and_decode_roundtrip():
    admin_id = uuid.uuid4()
    token = create_access_token(admin_id, "admin", is_superadmin=True)

    claims = _decode_access_token(token)

    assert claims["sub"] == str(admin_id)
    assert claims["username"] == "admin"
    assert claims["is_superadmin"] is True


def test_decode_rejects_garbage_token():
    with pytest.raises(HTTPException) as exc_info:
        _decode_access_token("not-a-real-token")
    assert exc_info.value.status_code == 401


def test_decode_rejects_token_signed_with_wrong_secret():
    bogus = jwt.encode({"sub": "x"}, "wrong-secret", algorithm=JWT_ALGORITHM)
    with pytest.raises(HTTPException) as exc_info:
        _decode_access_token(bogus)
    assert exc_info.value.status_code == 401
