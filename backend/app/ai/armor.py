"""Optional regional Model Armor screening. A configured screening failure blocks Ask."""

import asyncio
import re
from typing import Any, Protocol


class ContentScreen(Protocol):
    async def allow(self, text: str, *, is_response: bool = False) -> bool: ...


class ModelArmorScreen:
    def __init__(
        self, template_name: str, *, session: Any = None, timeout_seconds: float = 15
    ) -> None:
        match = re.fullmatch(
            r"projects/([a-z0-9:-]+)/locations/([a-z0-9-]+)/templates/([A-Za-z0-9_-]+)",
            template_name,
        )
        if not match:
            raise ValueError("Model Armor requires a fully qualified regional template name")
        self.url = f"https://modelarmor.{match[2]}.rep.googleapis.com/v1/{template_name}"
        self.session = session
        self.timeout_seconds = timeout_seconds

    def _check(self, text: str, is_response: bool) -> bool:
        if self.session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self.session = AuthorizedSession(credentials)
        operation = "sanitizeModelResponse" if is_response else "sanitizeUserPrompt"
        key = "modelResponseData" if is_response else "userPromptData"
        response = self.session.post(
            f"{self.url}:{operation}",
            json={key: {"text": text}},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        result = response.json().get("sanitizationResult", {})
        return (
            result.get("invocationResult") == "SUCCESS"
            and result.get("filterMatchState") == "NO_MATCH_FOUND"
        )

    async def allow(self, text: str, *, is_response: bool = False) -> bool:
        try:
            async with asyncio.timeout(self.timeout_seconds + 1):
                return await asyncio.to_thread(self._check, text, is_response)
        except Exception:
            return False
