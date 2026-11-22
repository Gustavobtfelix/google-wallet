from datetime import datetime
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import jwt

from app.services.wallet import SAVE_URL, WalletError, WalletService


@pytest.fixture(scope="module")
def service_account_info():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "type": "service_account",
        "client_email": "wallet@projeto-teste.iam.gserviceaccount.com",
        "private_key": pem,
        "private_key_id": "abc123",
    }


def _pass(**kw):
    data = dict(
        token="a1b2c3d4e5f60718293a4b5c6d7e8f90",
        short_code="A1B2C3D4",
        visitor_name="Maria Souza",
        company="ACME",
        host_name="João",
        purpose=None,
        status="ativo",
        visit_start=datetime(2030, 1, 10, 9, 0),
        visit_end=datetime(2030, 1, 10, 11, 0),
    )
    data.update(kw)
    return SimpleNamespace(**data)


def _service(info=None, issuer="3388000000012345678"):
    return WalletService(
        issuer_id=issuer,
        class_suffix="cartao_visitante",
        credentials_info=info,
        company_name="Minha Empresa",
        base_url="https://visitantes.exemplo.com/",
        timezone="America/Sao_Paulo",
    )


def test_build_object_fields():
    obj = _service().build_object(_pass())
    assert obj["id"] == "3388000000012345678.visitante_a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert obj["classId"] == "3388000000012345678.cartao_visitante"
    assert obj["state"] == "ACTIVE"
    assert obj["header"]["defaultValue"]["value"] == "Maria Souza"
    assert obj["barcode"]["value"] == "https://visitantes.exemplo.com/verificar/a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert obj["validTimeInterval"]["start"]["date"] == "2030-01-10T09:00:00-03:00"
    modules = {m["id"]: m["body"] for m in obj["textModulesData"]}
    assert modules["empresa"] == "ACME"
    assert modules["motivo"] == "-"  # campo vazio não pode ir em branco para a API


def test_revoked_pass_is_expired_in_wallet():
    assert _service().build_object(_pass(status="revogado"))["state"] == "EXPIRED"


def test_disabled_without_credentials():
    service = _service(info=None)
    assert not service.enabled
    with pytest.raises(WalletError):
        service.save_url(_pass())


def test_save_url_contains_signed_jwt(service_account_info):
    service = _service(info=service_account_info)
    url = service.save_url(_pass())
    assert url.startswith(SAVE_URL)
    claims = jwt.decode(url.removeprefix(SAVE_URL), verify=False)
    assert claims["iss"] == service_account_info["client_email"]
    assert claims["aud"] == "google"
    assert claims["typ"] == "savetowallet"
    assert claims["payload"]["genericObjects"][0]["id"].endswith("a1b2c3d4e5f60718293a4b5c6d7e8f90")
    assert claims["payload"]["genericClasses"][0]["id"] == service.class_id
