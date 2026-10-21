"""Optional Telegram delivery. The bot token only ever comes from the environment and is never
logged; failures are swallowed (and counted) so notification problems cannot affect monitoring."""

from __future__ import annotations

import logging

import httpx

from app.notifications.base import Notification

log = logging.getLogger(__name__)

ICONS = {"critical": "\U0001f534", "warning": "\U0001f7e0", "info": "\U0001f7e2", "resolved": "✅"}


class TelegramNotifier:
    name = "telegram"

    def __init__(
        self,
        token: str | None,
        chat_id: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._transport = transport
        self.failures = 0

    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def format(self, n: Notification) -> str:
        label = {"resolved": "RESOLVED", "test": "TEST", "reminder": "STILL ACTIVE"}.get(
            n.kind, n.severity.upper()
        )
        icon = ICONS["resolved"] if n.kind == "resolved" else ICONS.get(n.severity, "")
        return f"{icon} [{label}] {n.title}\n{n.message}"[:3500]

    async def send(self, notification: Notification) -> None:
        if not self.configured():
            raise RuntimeError("Telegram is not configured")
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": self.format(notification),
                        "disable_web_page_preview": True,
                    },
                )
            if resp.status_code != 200:
                self.failures += 1
                log.warning("telegram delivery failed: HTTP %s", resp.status_code)
                raise RuntimeError(f"Telegram returned HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            self.failures += 1
            # Do not log the exception text: httpx errors can include the request URL (token).
            log.warning("telegram delivery failed: %s", type(exc).__name__)
            raise RuntimeError("Could not reach Telegram") from None
