"""Integração com a Google Wallet API (Generic Pass).

Fluxo:
1. O sistema monta a *classe* (modelo visual comum a todos os cartões) e o *objeto*
   (o cartão de um visitante específico).
2. Ambos são colocados em um JWT assinado com a chave da conta de serviço do Google Cloud.
3. O link https://pay.google.com/gp/v/save/<jwt> é enviado ao visitante; ao abri-lo,
   o cartão é adicionado à carteira do celular dele.
4. Alterações posteriores (edição ou revogação) são enviadas via REST (PATCH) para
   que o cartão na carteira do visitante seja atualizado automaticamente.

Sem credenciais configuradas o serviço opera em "modo demonstração": o objeto do cartão
é gerado normalmente, mas nenhum link de salvamento é criado.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import current_app

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]
API_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
SAVE_URL = "https://pay.google.com/gp/v/save/"


class WalletError(Exception):
    pass


def _lv(value: str) -> dict:
    """LocalizedString exigido pela API."""
    return {"defaultValue": {"language": "pt-BR", "value": value}}


def _field(path: str) -> dict:
    return {"firstValue": {"fields": [{"fieldPath": path}]}}


class WalletService:
    def __init__(
        self,
        issuer_id: str,
        class_suffix: str,
        credentials_info: dict | None,
        company_name: str,
        base_url: str,
        timezone: str,
        logo_url: str = "",
        bg_color: str = "#1a73e8",
    ):
        self.issuer_id = issuer_id
        self.class_suffix = class_suffix
        self.credentials_info = credentials_info
        self.company_name = company_name
        self.base_url = base_url.rstrip("/")
        self.tz = ZoneInfo(timezone)
        self.logo_url = logo_url
        self.bg_color = bg_color

    @classmethod
    def from_app(cls, app=None) -> "WalletService":
        app = app or current_app
        cfg = app.config
        info = None
        cred_path = cfg.get("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and Path(cred_path).is_file():
            info = json.loads(Path(cred_path).read_text(encoding="utf-8"))
        return cls(
            issuer_id=cfg.get("WALLET_ISSUER_ID", ""),
            class_suffix=cfg.get("WALLET_CLASS_SUFFIX", "cartao_visitante"),
            credentials_info=info,
            company_name=cfg.get("COMPANY_NAME", ""),
            base_url=cfg.get("BASE_URL", ""),
            timezone=cfg.get("TIMEZONE", "America/Sao_Paulo"),
            logo_url=cfg.get("WALLET_LOGO_URL", ""),
            bg_color=cfg.get("WALLET_BG_COLOR", "#1a73e8"),
        )

    # ------------------------------------------------------------------ identificação
    @property
    def enabled(self) -> bool:
        return bool(self.issuer_id and self.credentials_info)

    @property
    def class_id(self) -> str:
        return f"{self.issuer_id or 'DEMO'}.{self.class_suffix}"

    def object_id(self, visitor_pass) -> str:
        return f"{self.issuer_id or 'DEMO'}.visitante_{visitor_pass.token}"

    def verify_url(self, visitor_pass) -> str:
        return f"{self.base_url}/verificar/{visitor_pass.token}"

    # ------------------------------------------------------------------ montagem
    def _iso(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        return dt.isoformat()

    @staticmethod
    def _fmt(dt: datetime) -> str:
        return dt.strftime("%d/%m/%Y %H:%M")

    def build_class(self) -> dict:
        return {
            "id": self.class_id,
            "classTemplateInfo": {
                "cardTemplateOverride": {
                    "cardRowTemplateInfos": [
                        {
                            "twoItems": {
                                "startItem": _field("object.textModulesData['empresa']"),
                                "endItem": _field("object.textModulesData['anfitriao']"),
                            }
                        },
                        {
                            "twoItems": {
                                "startItem": _field("object.textModulesData['entrada']"),
                                "endItem": _field("object.textModulesData['saida']"),
                            }
                        },
                    ]
                }
            },
        }

    def build_object(self, visitor_pass) -> dict:
        p = visitor_pass
        state = "EXPIRED" if p.status == "revogado" else "ACTIVE"
        obj = {
            "id": self.object_id(p),
            "classId": self.class_id,
            "state": state,
            "cardTitle": _lv(self.company_name or "Cartão de Visitante"),
            "subheader": _lv("Visitante"),
            "header": _lv(p.visitor_name),
            "hexBackgroundColor": self.bg_color,
            "textModulesData": [
                {"id": "empresa", "header": "Empresa", "body": p.company or "-"},
                {"id": "anfitriao", "header": "Anfitrião", "body": p.host_name},
                {"id": "entrada", "header": "Entrada", "body": self._fmt(p.visit_start)},
                {"id": "saida", "header": "Saída", "body": self._fmt(p.visit_end)},
                {"id": "motivo", "header": "Motivo da visita", "body": p.purpose or "-"},
            ],
            "barcode": {
                "type": "QR_CODE",
                "value": self.verify_url(p),
                "alternateText": p.short_code,
            },
            "validTimeInterval": {
                "start": {"date": self._iso(p.visit_start)},
                "end": {"date": self._iso(p.visit_end)},
            },
        }
        if self.logo_url:
            obj["logo"] = {
                "sourceUri": {"uri": self.logo_url},
                "contentDescription": _lv(self.company_name),
            }
        return obj

    # ------------------------------------------------------------------ link "Salvar no Google Wallet"
    def create_save_jwt(self, visitor_pass) -> str:
        if not self.enabled:
            raise WalletError("Google Wallet não configurado (WALLET_ISSUER_ID / credenciais).")
        from google.auth import crypt, jwt

        claims = {
            "iss": self.credentials_info["client_email"],
            "aud": "google",
            "typ": "savetowallet",
            "origins": [],
            "payload": {
                "genericClasses": [self.build_class()],
                "genericObjects": [self.build_object(visitor_pass)],
            },
        }
        signer = crypt.RSASigner.from_service_account_info(self.credentials_info)
        token = jwt.encode(signer, claims)
        return token.decode("utf-8") if isinstance(token, bytes) else token

    def save_url(self, visitor_pass) -> str:
        return SAVE_URL + self.create_save_jwt(visitor_pass)

    # ------------------------------------------------------------------ atualização via REST
    def _session(self):
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_info(
            self.credentials_info, scopes=SCOPES
        )
        return AuthorizedSession(creds)

    def sync_object(self, visitor_pass) -> bool:
        """Envia o estado atual do cartão para a Google Wallet.

        Retorna False se o visitante ainda não salvou o cartão (objeto inexistente).
        """
        if not self.enabled:
            return False
        url = f"{API_BASE}/genericObject/{self.object_id(visitor_pass)}"
        resp = self._session().patch(url, json=self.build_object(visitor_pass), timeout=15)
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            log.error("Erro Google Wallet %s: %s", resp.status_code, resp.text)
            raise WalletError(f"Google Wallet respondeu {resp.status_code}")
        return True
