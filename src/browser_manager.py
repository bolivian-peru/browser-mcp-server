"""Browser instance management via browser.proxies.sx HTTP API.

Adapted from nodriver-based local browser management to cloud antidetect
browser sessions with auto-allocated mobile proxy and Identity Bundles.

Original: https://github.com/vibheksoni/stealth-browser-mcp
Adapted for: https://browser.proxies.sx
"""

import asyncio
import os
import json
from typing import Dict, Optional, List, Any
from datetime import datetime

import aiohttp

from models import BrowserInstance, BrowserState, BrowserOptions, PageState


API_BASE = os.environ.get("BROWSER_API_URL", "https://browser.proxies.sx")


class BrowserManager:
    """Manages browser sessions via browser.proxies.sx API."""

    def __init__(self):
        self._instances: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._http: Optional[aiohttp.ClientSession] = None

    async def _get_http(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        return self._http

    async def spawn_browser(self, options: BrowserOptions) -> BrowserInstance:
        """
        Create a new browser session via browser.proxies.sx API.
        Requires x402 USDC payment or an internal key.
        """
        instance = BrowserInstance(
            instance_id="pending",
            headless=True,
            user_agent=options.user_agent,
            viewport={"width": options.viewport_width, "height": options.viewport_height},
        )

        try:
            http = await self._get_http()

            body: Dict[str, Any] = {}
            if hasattr(options, "country") and options.country:
                body["country"] = options.country
            if hasattr(options, "duration_minutes") and options.duration_minutes:
                body["durationMinutes"] = options.duration_minutes
            else:
                body["durationMinutes"] = 60
            if hasattr(options, "profile_id") and options.profile_id:
                body["profile_id"] = options.profile_id

            headers: Dict[str, str] = {"Content-Type": "application/json"}

            payment_sig = getattr(options, "payment_signature", None) or os.environ.get("PAYMENT_SIGNATURE")
            if payment_sig:
                headers["Payment-Signature"] = payment_sig

            internal_key = os.environ.get("BROWSER_INTERNAL_KEY")
            if internal_key:
                headers["X-Internal-Key"] = internal_key

            async with http.post(f"{API_BASE}/v1/sessions", json=body, headers=headers) as resp:
                data = await resp.json()

                if resp.status == 402:
                    instance.state = BrowserState.ERROR
                    instance.instance_id = "payment_required"
                    async with self._lock:
                        self._instances["payment_required"] = {
                            "instance": instance,
                            "session_id": None,
                            "session_token": None,
                            "payment_info": data,
                        }
                    raise PaymentRequiredError(data)

                if resp.status not in (200, 201):
                    raise Exception(data.get("error", f"API error {resp.status}"))

                session_id = data.get("session_id")
                session_token = data.get("session_token", session_id)

                instance.instance_id = session_id
                instance.state = BrowserState.READY

                async with self._lock:
                    self._instances[session_id] = {
                        "instance": instance,
                        "session_id": session_id,
                        "session_token": session_token,
                        "expires_at": data.get("expires_at") or data.get("expiresAt"),
                        "proxy": data.get("proxy", {}),
                        "fingerprint": data.get("fingerprint", {}),
                        "loaded_profile_id": data.get("loaded_profile_id"),
                    }

            return instance

        except PaymentRequiredError:
            raise
        except Exception as e:
            instance.state = BrowserState.ERROR
            raise Exception(f"Failed to create browser session: {str(e)}")

    async def send_command(
        self, instance_id: str, action: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a command to the browser session."""
        async with self._lock:
            session = self._instances.get(instance_id)
        if not session:
            raise Exception(f"No browser instance: {instance_id}")

        http = await self._get_http()
        sid = session["session_id"]
        token = session["session_token"]

        body: Dict[str, Any] = {"action": action}
        if params:
            body.update(params)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        async with http.post(
            f"{API_BASE}/v1/sessions/{sid}/command", json=body, headers=headers
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(data.get("error", f"Command failed: {resp.status}"))
            return data

    async def navigate(self, instance_id: str, url: str, wait_until: str = "domcontentloaded") -> Dict[str, Any]:
        """Navigate to a URL."""
        result = await self.send_command(instance_id, "navigate", {"url": url, "wait_until": wait_until})
        async with self._lock:
            session = self._instances.get(instance_id)
            if session:
                session["instance"].current_url = result.get("url", url)
                session["instance"].title = result.get("title", "")
                session["instance"].state = BrowserState.READY
                session["instance"].update_activity()
        return result

    async def click(self, instance_id: str, selector: str) -> Dict[str, Any]:
        return await self.send_command(instance_id, "click", {"selector": selector})

    async def type_text(self, instance_id: str, selector: str, text: str, human_like: bool = True) -> Dict[str, Any]:
        action = "type_slow" if human_like else "type"
        return await self.send_command(instance_id, action, {"selector": selector, "text": text})

    async def screenshot(self, instance_id: str, full_page: bool = False) -> Dict[str, Any]:
        return await self.send_command(instance_id, "screenshot", {"full_page": full_page})

    async def get_content(self, instance_id: str) -> Dict[str, Any]:
        return await self.send_command(instance_id, "content")

    async def get_text(self, instance_id: str, selector: str = "body") -> Dict[str, Any]:
        return await self.send_command(instance_id, "text", {"selector": selector})

    async def execute_script(self, instance_id: str, script: str) -> Dict[str, Any]:
        return await self.send_command(instance_id, "evaluate", {"script": script})

    async def get_cookies(self, instance_id: str) -> Dict[str, Any]:
        return await self.send_command(instance_id, "cookies")

    async def set_cookie(self, instance_id: str, cookie: Dict[str, Any]) -> Dict[str, Any]:
        return await self.send_command(instance_id, "set_cookie", {"cookie": cookie})

    async def clear_cookies(self, instance_id: str) -> Dict[str, Any]:
        return await self.send_command(instance_id, "clear_cookies")

    async def get_local_storage(self, instance_id: str) -> Dict[str, Any]:
        return await self.send_command(instance_id, "local_storage")

    async def set_local_storage(self, instance_id: str, items: Dict[str, str]) -> Dict[str, Any]:
        return await self.send_command(instance_id, "set_local_storage", {"items": items})

    async def wait_for_element(self, instance_id: str, selector: str, timeout: int = 10000) -> Dict[str, Any]:
        return await self.send_command(instance_id, "wait", {"selector": selector, "timeout": timeout})

    async def press_key(self, instance_id: str, key: str) -> Dict[str, Any]:
        return await self.send_command(instance_id, "press", {"key": key})

    async def scroll(self, instance_id: str, x: int = 0, y: int = 0) -> Dict[str, Any]:
        return await self.send_command(instance_id, "scroll", {"x": x, "y": y})

    # --- Identity Bundle Methods ---

    async def save_profile(self, instance_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Save Identity Bundle (cookies + localStorage + fingerprint + proxy binding)."""
        async with self._lock:
            session = self._instances.get(instance_id)
        if not session:
            raise Exception(f"No browser instance: {instance_id}")

        http = await self._get_http()
        sid = session["session_id"]
        token = session["session_token"]
        body = {"name": name} if name else {}

        async with http.post(
            f"{API_BASE}/v1/sessions/{sid}/profile",
            json=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(data.get("error", f"Save profile failed: {resp.status}"))
            return data

    async def load_profile(self, instance_id: str, profile_id: str) -> Dict[str, Any]:
        """Load Identity Bundle into current session."""
        async with self._lock:
            session = self._instances.get(instance_id)
        if not session:
            raise Exception(f"No browser instance: {instance_id}")

        http = await self._get_http()
        sid = session["session_id"]
        token = session["session_token"]

        async with http.post(
            f"{API_BASE}/v1/sessions/{sid}/profile/load",
            json={"profile_id": profile_id},
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(data.get("error", f"Load profile failed: {resp.status}"))
            return data

    async def list_profiles(self, instance_id: str) -> Dict[str, Any]:
        """List all saved Identity Bundle profiles."""
        async with self._lock:
            session = self._instances.get(instance_id)
        if not session:
            raise Exception(f"No browser instance: {instance_id}")

        http = await self._get_http()
        token = session["session_token"]

        async with http.get(
            f"{API_BASE}/v1/profiles",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(data.get("error", f"List profiles failed: {resp.status}"))
            return data

    async def delete_profile(self, profile_id: str, instance_id: str) -> Dict[str, Any]:
        """Delete a saved profile."""
        async with self._lock:
            session = self._instances.get(instance_id)
        if not session:
            raise Exception(f"No browser instance: {instance_id}")

        http = await self._get_http()
        token = session["session_token"]

        async with http.delete(
            f"{API_BASE}/v1/profiles/{profile_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(data.get("error", f"Delete profile failed: {resp.status}"))
            return data

    # --- Session Management ---

    def get_instance(self, instance_id: str) -> Optional[BrowserInstance]:
        session = self._instances.get(instance_id)
        return session["instance"] if session else None

    def get_session_data(self, instance_id: str) -> Optional[dict]:
        return self._instances.get(instance_id)

    def get_tab(self, instance_id: str):
        """Compatibility shim — returns proxy object that routes to API."""
        return APITab(self, instance_id)

    async def get_page_state(self, instance_id: str) -> PageState:
        cookies_data = await self.get_cookies(instance_id)
        session = self._instances.get(instance_id)
        inst = session["instance"] if session else None

        return PageState(
            instance_id=instance_id,
            url=inst.current_url or "" if inst else "",
            title=inst.title or "" if inst else "",
            ready_state="complete",
            cookies=cookies_data.get("cookies", []),
            viewport=inst.viewport if inst else {"width": 1920, "height": 1080},
        )

    async def close_browser(self, instance_id: str) -> bool:
        async with self._lock:
            session = self._instances.get(instance_id)
        if not session:
            return False

        try:
            http = await self._get_http()
            sid = session["session_id"]
            token = session["session_token"]
            async with http.delete(
                f"{API_BASE}/v1/sessions/{sid}",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                pass
            async with self._lock:
                del self._instances[instance_id]
            return True
        except Exception:
            async with self._lock:
                if instance_id in self._instances:
                    del self._instances[instance_id]
            return True

    async def close_all(self):
        async with self._lock:
            ids = list(self._instances.keys())
        for iid in ids:
            try:
                await self.close_browser(iid)
            except Exception:
                pass

    def list_instances(self) -> List[BrowserInstance]:
        return [s["instance"] for s in self._instances.values() if s.get("instance")]

    async def cleanup(self):
        await self.close_all()
        if self._http and not self._http.closed:
            await self._http.close()


class APITab:
    """Compatibility shim that mimics a nodriver Tab for code that expects it."""

    def __init__(self, manager: BrowserManager, instance_id: str):
        self._manager = manager
        self._instance_id = instance_id

    async def evaluate(self, script: str):
        result = await self._manager.execute_script(self._instance_id, script)
        return result.get("result")

    async def get(self, url: str):
        return await self._manager.navigate(self._instance_id, url)

    async def send(self, *args, **kwargs):
        raise NotImplementedError(
            "Direct CDP commands not available in cloud browser mode. "
            "Use browser_manager.send_command() or execute_script() instead."
        )


class PaymentRequiredError(Exception):
    """Raised when x402 payment is required."""

    def __init__(self, payment_info: dict):
        self.payment_info = payment_info
        networks = payment_info.get("networks", [])
        addrs = ", ".join(f"{n.get('network')}: {n.get('address')}" for n in networks)
        price = payment_info.get("price", 0)
        if isinstance(price, (int, float)) and price > 1000:
            price_usd = price / 1_000_000
        elif isinstance(price, dict):
            price_usd = float(price.get("amount", 0))
        else:
            price_usd = float(price)
        super().__init__(f"Payment required: ${price_usd:.3f} USDC. Send to: {addrs}")
