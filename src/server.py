"""
browser.proxies.sx MCP Server v1.1.0

Cloud antidetect browser automation via the browser.proxies.sx HTTP API.
Replaces local nodriver/CDP with cloud browser sessions that include:
  - Auto-allocated mobile proxy (6 countries: US/GB/DE/FR/ES/PL)
  - Camoufox antidetect fingerprint
  - Identity Bundles (persistent cookies, localStorage, fingerprint)
  - x402 USDC micropayments (Base + Solana)

Pricing: $0.005/min ($0.30/hr) — single flat rate.

Adapted from: https://github.com/vibheksoni/stealth-browser-mcp
API docs: https://browser.proxies.sx
"""

import asyncio
import base64
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from browser_manager import BrowserManager, PaymentRequiredError
from models import BrowserOptions, BrowserState, PageState, ScriptResult


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def app_lifespan(server):
    """Manage application lifecycle with proper cleanup."""
    print("[browser.proxies.sx] MCP Server starting...")
    try:
        yield
    finally:
        print("[browser.proxies.sx] Shutting down, closing cloud sessions...")
        try:
            await browser_manager.cleanup()
            print("[browser.proxies.sx] All sessions closed.")
        except Exception as e:
            print(f"[browser.proxies.sx] Cleanup error: {e}")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="browser.proxies.sx MCP Server",
    version="1.1.0",
    instructions="""
    Cloud antidetect browser automation via browser.proxies.sx.

    Key features:
    - Spawn cloud Camoufox browser sessions with auto-allocated mobile proxies
    - Navigate and interact with web pages (click, type, scroll, screenshot)
    - Execute JavaScript in page context
    - Manage cookies and localStorage
    - Identity Bundles: save/load persistent browser profiles (cookies + localStorage + fingerprint)
    - x402 USDC micropayments on Base or Solana ($0.005/min)

    Available countries: US, GB, DE, FR, ES, PL

    Payment: Provide a payment_signature (x402 tx hash) when spawning,
    or set BROWSER_INTERNAL_KEY env var for internal/testing access.

    All browser instances run in the cloud — no local Chrome/Chromium needed.
    """,
    lifespan=app_lifespan,
)

browser_manager = BrowserManager()


# ===========================================================================
# SECTION 1: Browser Management
# ===========================================================================

@mcp.tool()
async def spawn_browser(
    country: Optional[str] = None,
    duration_minutes: int = 60,
    profile_id: Optional[str] = None,
    payment_signature: Optional[str] = None,
    user_agent: Optional[str] = None,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
) -> Dict[str, Any]:
    """
    Spawn a new cloud antidetect browser session via browser.proxies.sx.

    The session includes an auto-allocated mobile proxy and Camoufox fingerprint.
    Requires x402 USDC payment or BROWSER_INTERNAL_KEY env var.

    Pricing: $0.005/min ($0.30/hr). Duration range: 15-480 minutes.

    Args:
        country: Proxy country code (US, GB, DE, FR, ES, PL). Random if omitted.
        duration_minutes: Session length in minutes (15-480, default 60).
        profile_id: Identity Bundle ID to restore (cookies, localStorage, fingerprint).
        payment_signature: x402 USDC transaction hash (Base or Solana chain).
        user_agent: Optional user-agent override.
        viewport_width: Viewport width in pixels (default 1920).
        viewport_height: Viewport height in pixels (default 1080).

    Returns:
        Session info including instance_id, proxy details, fingerprint, and expiry.
        If payment is required, returns payment instructions with wallet addresses.
    """
    try:
        options = BrowserOptions(
            country=country,
            duration_minutes=duration_minutes,
            profile_id=profile_id,
            payment_signature=payment_signature,
            user_agent=user_agent,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        instance = await browser_manager.spawn_browser(options)
        session_data = browser_manager.get_session_data(instance.instance_id) or {}

        result = {
            "instance_id": instance.instance_id,
            "state": instance.state.value,
            "viewport": instance.viewport,
            "expires_at": session_data.get("expires_at"),
        }

        proxy_info = session_data.get("proxy", {})
        if proxy_info:
            result["proxy"] = {
                "country": proxy_info.get("country"),
                "city": proxy_info.get("city"),
                "carrier": proxy_info.get("carrier"),
                "ip": proxy_info.get("ip"),
            }

        fingerprint_info = session_data.get("fingerprint", {})
        if fingerprint_info:
            result["fingerprint"] = {
                "os": fingerprint_info.get("os"),
                "browser": fingerprint_info.get("browser"),
                "platform": fingerprint_info.get("platform"),
            }

        loaded_profile = session_data.get("loaded_profile_id")
        if loaded_profile:
            result["loaded_profile_id"] = loaded_profile

        return result

    except PaymentRequiredError as e:
        pi = e.payment_info
        networks = pi.get("networks", [])
        price = pi.get("price", 0)
        if isinstance(price, (int, float)) and price > 1000:
            price_usd = price / 1_000_000
        elif isinstance(price, dict):
            price_usd = float(price.get("amount", 0))
        else:
            price_usd = float(price)

        return {
            "status": "payment_required",
            "price_usdc": round(price_usd, 4),
            "message": f"Send ${price_usd:.4f} USDC to one of the addresses below, then retry with the tx hash as payment_signature.",
            "networks": [
                {
                    "network": n.get("network"),
                    "address": n.get("address"),
                    "token": n.get("token", "USDC"),
                }
                for n in networks
            ],
            "instructions": [
                "1. Send the exact USDC amount to one of the wallet addresses above.",
                "2. Wait for the transaction to confirm (~2s Base, ~400ms Solana).",
                "3. Call spawn_browser again with payment_signature set to the tx hash.",
            ],
        }
    except Exception as e:
        raise Exception(f"Failed to spawn browser: {str(e)}")


@mcp.tool()
async def list_instances() -> List[Dict[str, Any]]:
    """
    List all active cloud browser sessions.

    Returns:
        List of browser instances with their current state.
    """
    instances = browser_manager.list_instances()
    result = []
    for inst in instances:
        data = browser_manager.get_session_data(inst.instance_id) or {}
        entry = {
            "instance_id": inst.instance_id,
            "state": inst.state.value,
            "current_url": inst.current_url,
            "title": inst.title,
            "expires_at": data.get("expires_at"),
        }
        proxy_info = data.get("proxy", {})
        if proxy_info:
            entry["proxy_country"] = proxy_info.get("country")
        result.append(entry)
    return result


@mcp.tool()
async def close_instance(instance_id: str) -> Dict[str, Any]:
    """
    Close a cloud browser session and release resources.

    Args:
        instance_id: Browser instance ID.

    Returns:
        Success status.
    """
    success = await browser_manager.close_browser(instance_id)
    return {"success": success, "instance_id": instance_id}


@mcp.tool()
async def get_instance_state(instance_id: str) -> Dict[str, Any]:
    """
    Get detailed state of a browser instance.

    Args:
        instance_id: Browser instance ID.

    Returns:
        Complete state information including URL, title, cookies, viewport.
    """
    try:
        state = await browser_manager.get_page_state(instance_id)
        if state:
            return state.model_dump() if hasattr(state, "model_dump") else state.dict()
    except Exception:
        pass

    inst = browser_manager.get_instance(instance_id)
    if inst:
        return {
            "instance_id": inst.instance_id,
            "state": inst.state.value,
            "current_url": inst.current_url,
            "title": inst.title,
        }
    return {"error": f"Instance not found: {instance_id}"}


# ===========================================================================
# SECTION 2: Navigation
# ===========================================================================

@mcp.tool()
async def navigate(
    instance_id: str,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout: int = 30000,
) -> Dict[str, Any]:
    """
    Navigate to a URL.

    Args:
        instance_id: Browser instance ID.
        url: URL to navigate to.
        wait_until: Wait condition — 'load', 'domcontentloaded', or 'networkidle'.
        timeout: Navigation timeout in milliseconds (default 30000).

    Returns:
        Navigation result with final URL and title.
    """
    if isinstance(timeout, str):
        timeout = int(timeout)
    result = await browser_manager.navigate(instance_id, url, wait_until)
    return {
        "url": result.get("url", url),
        "title": result.get("title", ""),
        "success": True,
    }


@mcp.tool()
async def go_back(instance_id: str) -> Dict[str, Any]:
    """
    Navigate back in browser history.

    Args:
        instance_id: Browser instance ID.

    Returns:
        Success status.
    """
    result = await browser_manager.execute_script(instance_id, "history.back()")
    return {"success": True}


@mcp.tool()
async def go_forward(instance_id: str) -> Dict[str, Any]:
    """
    Navigate forward in browser history.

    Args:
        instance_id: Browser instance ID.

    Returns:
        Success status.
    """
    result = await browser_manager.execute_script(instance_id, "history.forward()")
    return {"success": True}


@mcp.tool()
async def reload_page(instance_id: str) -> Dict[str, Any]:
    """
    Reload the current page.

    Args:
        instance_id: Browser instance ID.

    Returns:
        Success status.
    """
    result = await browser_manager.execute_script(instance_id, "location.reload()")
    return {"success": True}


# ===========================================================================
# SECTION 3: Element Interaction
# ===========================================================================

@mcp.tool()
async def click_element(
    instance_id: str,
    selector: str,
) -> Dict[str, Any]:
    """
    Click an element on the page.

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector for the element to click.

    Returns:
        Click result.
    """
    result = await browser_manager.click(instance_id, selector)
    return {"success": True, **result}


@mcp.tool()
async def type_text(
    instance_id: str,
    selector: str,
    text: str,
    human_like: bool = True,
) -> Dict[str, Any]:
    """
    Type text into an input field with optional human-like delay.

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector for the input element.
        text: Text to type.
        human_like: If True, types slowly to mimic human input (default True).

    Returns:
        Typing result.
    """
    result = await browser_manager.type_text(instance_id, selector, text, human_like)
    return {"success": True, **result}


@mcp.tool()
async def paste_text(
    instance_id: str,
    selector: str,
    text: str,
) -> Dict[str, Any]:
    """
    Paste text instantly into an input field (no keystroke delay).

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector for the input element.
        text: Text to paste.

    Returns:
        Paste result.
    """
    result = await browser_manager.type_text(instance_id, selector, text, human_like=False)
    return {"success": True, **result}


@mcp.tool()
async def press_key(
    instance_id: str,
    key: str,
) -> Dict[str, Any]:
    """
    Press a keyboard key (Enter, Tab, Escape, etc.).

    Args:
        instance_id: Browser instance ID.
        key: Key to press (e.g. 'Enter', 'Tab', 'Escape', 'ArrowDown').

    Returns:
        Key press result.
    """
    result = await browser_manager.press_key(instance_id, key)
    return {"success": True, **result}


@mcp.tool()
async def select_option(
    instance_id: str,
    selector: str,
    value: Optional[str] = None,
    text: Optional[str] = None,
    index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Select an option from a dropdown <select> element.

    Provide one of: value, text, or index.

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector for the <select> element.
        value: Option value attribute to select.
        text: Option visible text to select.
        index: Option index (0-based) to select.

    Returns:
        Selection result.
    """
    if value is not None:
        script = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ error: 'Element not found' }};
            el.value = {json.dumps(value)};
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return {{ selected: el.value }};
        }})()
        """
    elif text is not None:
        script = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ error: 'Element not found' }};
            const opt = Array.from(el.options).find(o => o.text === {json.dumps(text)});
            if (!opt) return {{ error: 'Option not found' }};
            el.value = opt.value;
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return {{ selected: opt.value, text: opt.text }};
        }})()
        """
    elif index is not None:
        if isinstance(index, str):
            index = int(index)
        script = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ error: 'Element not found' }};
            if ({index} >= el.options.length) return {{ error: 'Index out of range' }};
            el.selectedIndex = {index};
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return {{ selected: el.value, index: {index} }};
        }})()
        """
    else:
        return {"success": False, "error": "Provide one of: value, text, or index"}

    result = await browser_manager.execute_script(instance_id, script)
    r = result.get("result", {})
    if isinstance(r, dict) and r.get("error"):
        return {"success": False, "error": r["error"]}
    return {"success": True, **result}


@mcp.tool()
async def wait_for_element(
    instance_id: str,
    selector: str,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """
    Wait for an element to appear on the page.

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector to wait for.
        timeout: Timeout in milliseconds (default 10000).

    Returns:
        Whether the element was found.
    """
    if isinstance(timeout, str):
        timeout = int(timeout)
    result = await browser_manager.wait_for_element(instance_id, selector, timeout)
    return {"found": True, **result}


@mcp.tool()
async def scroll_page(
    instance_id: str,
    direction: str = "down",
    amount: int = 500,
) -> Dict[str, Any]:
    """
    Scroll the page.

    Args:
        instance_id: Browser instance ID.
        direction: 'down', 'up', 'left', 'right', 'top', or 'bottom'.
        amount: Pixels to scroll (ignored for 'top' and 'bottom').

    Returns:
        Scroll result.
    """
    if isinstance(amount, str):
        amount = int(amount)

    scroll_map = {
        "down": (0, amount),
        "up": (0, -amount),
        "right": (amount, 0),
        "left": (-amount, 0),
    }

    if direction == "top":
        result = await browser_manager.execute_script(instance_id, "window.scrollTo(0, 0)")
        return {"success": True, "scrolled_to": "top"}
    elif direction == "bottom":
        result = await browser_manager.execute_script(
            instance_id, "window.scrollTo(0, document.body.scrollHeight)"
        )
        return {"success": True, "scrolled_to": "bottom"}
    else:
        x, y = scroll_map.get(direction, (0, amount))
        result = await browser_manager.scroll(instance_id, x, y)
        return {"success": True, "direction": direction, "amount": amount, **result}


@mcp.tool()
async def query_elements(
    instance_id: str,
    selector: str,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Query DOM elements matching a CSS selector and return their info.

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector to query.
        limit: Maximum number of elements to return (default 20).

    Returns:
        List of matching elements with tag, text, attributes, and visibility.
    """
    if isinstance(limit, str):
        limit = int(limit)
    script = f"""
    (() => {{
        const els = document.querySelectorAll({json.dumps(selector)});
        const results = [];
        const max = Math.min(els.length, {limit});
        for (let i = 0; i < max; i++) {{
            const el = els[i];
            const rect = el.getBoundingClientRect();
            const attrs = {{}};
            for (const a of el.attributes) {{ attrs[a.name] = a.value; }}
            results.push({{
                index: i,
                tag: el.tagName.toLowerCase(),
                text: (el.textContent || '').trim().substring(0, 200),
                attributes: attrs,
                visible: rect.width > 0 && rect.height > 0,
                bounding_box: {{ x: rect.x, y: rect.y, width: rect.width, height: rect.height }},
            }});
        }}
        return {{ total: els.length, returned: results.length, elements: results }};
    }})()
    """
    result = await browser_manager.execute_script(instance_id, script)
    return result.get("result", result)


@mcp.tool()
async def get_element_state(
    instance_id: str,
    selector: str,
) -> Dict[str, Any]:
    """
    Get complete state of a specific element (attributes, visibility, position, value).

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector for the element.

    Returns:
        Element state including tag, text, attributes, computed styles, bounding box, and form value.
    """
    script = f"""
    (() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) return {{ error: 'Element not found' }};
        const rect = el.getBoundingClientRect();
        const cs = window.getComputedStyle(el);
        const attrs = {{}};
        for (const a of el.attributes) {{ attrs[a.name] = a.value; }}
        return {{
            tag: el.tagName.toLowerCase(),
            text: (el.textContent || '').trim().substring(0, 500),
            inner_html: el.innerHTML.substring(0, 1000),
            attributes: attrs,
            value: el.value !== undefined ? el.value : null,
            checked: el.checked !== undefined ? el.checked : null,
            disabled: el.disabled || false,
            visible: rect.width > 0 && rect.height > 0,
            bounding_box: {{ x: rect.x, y: rect.y, width: rect.width, height: rect.height }},
            computed_style: {{
                display: cs.display,
                visibility: cs.visibility,
                opacity: cs.opacity,
                color: cs.color,
                background: cs.background,
                font_size: cs.fontSize,
                position: cs.position,
            }},
        }};
    }})()
    """
    result = await browser_manager.execute_script(instance_id, script)
    return result.get("result", result)


# ===========================================================================
# SECTION 4: Page Content & Screenshots
# ===========================================================================

@mcp.tool()
async def get_page_content(
    instance_id: str,
) -> Dict[str, Any]:
    """
    Get the current page HTML content.

    Args:
        instance_id: Browser instance ID.

    Returns:
        Page HTML content and metadata.
    """
    result = await browser_manager.get_content(instance_id)
    return result


@mcp.tool()
async def get_page_text(
    instance_id: str,
    selector: str = "body",
) -> Dict[str, Any]:
    """
    Get text content of the page or a specific element.

    Args:
        instance_id: Browser instance ID.
        selector: CSS selector (default 'body' for full page text).

    Returns:
        Text content.
    """
    result = await browser_manager.get_text(instance_id, selector)
    return result


@mcp.tool()
async def take_screenshot(
    instance_id: str,
    full_page: bool = False,
) -> Dict[str, Any]:
    """
    Take a screenshot of the current page.

    Args:
        instance_id: Browser instance ID.
        full_page: Capture full page (not just viewport).

    Returns:
        Screenshot as base64-encoded PNG data, or API response with image URL.
    """
    result = await browser_manager.screenshot(instance_id, full_page)
    # The API may return base64 data or a URL
    if isinstance(result, dict):
        b64 = result.get("screenshot") or result.get("data") or result.get("base64")
        if b64:
            return {"format": "png", "data": b64}
        return result
    return {"data": result}


@mcp.tool()
async def execute_script(
    instance_id: str,
    script: str,
) -> Dict[str, Any]:
    """
    Execute JavaScript in the page context.

    Args:
        instance_id: Browser instance ID.
        script: JavaScript code to execute.

    Returns:
        Script execution result.
    """
    try:
        result = await browser_manager.execute_script(instance_id, script)
        return {"success": True, "result": result.get("result"), "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


# ===========================================================================
# SECTION 5: Cookies & Storage
# ===========================================================================

@mcp.tool()
async def get_cookies(instance_id: str) -> Dict[str, Any]:
    """
    Get all cookies for the current page.

    Args:
        instance_id: Browser instance ID.

    Returns:
        List of cookies.
    """
    result = await browser_manager.get_cookies(instance_id)
    return result


@mcp.tool()
async def set_cookie(
    instance_id: str,
    name: str,
    value: str,
    domain: Optional[str] = None,
    path: str = "/",
    secure: bool = False,
    http_only: bool = False,
    same_site: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set a cookie.

    Args:
        instance_id: Browser instance ID.
        name: Cookie name.
        value: Cookie value.
        domain: Cookie domain.
        path: Cookie path (default '/').
        secure: Secure flag.
        http_only: HttpOnly flag.
        same_site: SameSite attribute ('Strict', 'Lax', 'None').

    Returns:
        Cookie set result.
    """
    cookie: Dict[str, Any] = {
        "name": name,
        "value": value,
        "path": path,
        "secure": secure,
        "httpOnly": http_only,
    }
    if domain:
        cookie["domain"] = domain
    if same_site:
        cookie["sameSite"] = same_site

    result = await browser_manager.set_cookie(instance_id, cookie)
    return {"success": True, **result}


@mcp.tool()
async def clear_cookies(instance_id: str) -> Dict[str, Any]:
    """
    Clear all cookies for the current session.

    Args:
        instance_id: Browser instance ID.

    Returns:
        Clear result.
    """
    result = await browser_manager.clear_cookies(instance_id)
    return {"success": True, **result}


@mcp.tool()
async def get_local_storage(instance_id: str) -> Dict[str, Any]:
    """
    Get all localStorage key-value pairs for the current page.

    Args:
        instance_id: Browser instance ID.

    Returns:
        localStorage data.
    """
    result = await browser_manager.get_local_storage(instance_id)
    return result


@mcp.tool()
async def set_local_storage(
    instance_id: str,
    items: Dict[str, str] = None,
    key: Optional[str] = None,
    value: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set localStorage items for the current page.

    Provide either `items` dict for bulk set, or `key`+`value` for single item.

    Args:
        instance_id: Browser instance ID.
        items: Dictionary of key-value pairs to set.
        key: Single key to set (use with value).
        value: Single value to set (use with key).

    Returns:
        Set result.
    """
    if items is None:
        items = {}
    if key is not None and value is not None:
        items[key] = value
    if not items:
        return {"success": False, "error": "Provide items dict or key+value pair"}

    result = await browser_manager.set_local_storage(instance_id, items)
    return {"success": True, **result}


# ===========================================================================
# SECTION 6: Identity Bundles (Profile Management)
# ===========================================================================

@mcp.tool()
async def save_profile(
    instance_id: str,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save the current session as an Identity Bundle.

    Captures cookies, localStorage, fingerprint, and proxy binding.
    The bundle can be restored later with load_profile or passed to spawn_browser.

    Args:
        instance_id: Browser instance ID.
        name: Optional human-readable name for the profile.

    Returns:
        Profile info including profile_id.
    """
    result = await browser_manager.save_profile(instance_id, name)
    return result


@mcp.tool()
async def load_profile(
    instance_id: str,
    profile_id: str,
) -> Dict[str, Any]:
    """
    Load an Identity Bundle into the current browser session.

    Restores cookies, localStorage, and fingerprint from a previously saved profile.

    Args:
        instance_id: Browser instance ID.
        profile_id: Identity Bundle ID to load.

    Returns:
        Load result.
    """
    result = await browser_manager.load_profile(instance_id, profile_id)
    return result


@mcp.tool()
async def list_profiles(
    instance_id: str,
) -> Dict[str, Any]:
    """
    List all saved Identity Bundle profiles.

    Args:
        instance_id: Browser instance ID (used for authentication).

    Returns:
        List of saved profiles with IDs, names, and metadata.
    """
    result = await browser_manager.list_profiles(instance_id)
    return result


@mcp.tool()
async def delete_profile(
    instance_id: str,
    profile_id: str,
) -> Dict[str, Any]:
    """
    Delete a saved Identity Bundle profile.

    Args:
        instance_id: Browser instance ID (used for authentication).
        profile_id: Profile ID to delete.

    Returns:
        Deletion result.
    """
    result = await browser_manager.delete_profile(profile_id, instance_id)
    return result


# ===========================================================================
# SECTION 7: Resources (MCP Resources)
# ===========================================================================

@mcp.resource("browser://{instance_id}/state")
async def get_browser_state_resource(instance_id: str) -> str:
    """
    Get current state of a browser instance as a resource.

    Args:
        instance_id: Browser instance ID.

    Returns:
        JSON string of the browser state.
    """
    try:
        state = await browser_manager.get_page_state(instance_id)
        if state:
            d = state.model_dump() if hasattr(state, "model_dump") else state.dict()
            return json.dumps(d, indent=2, default=str)
    except Exception:
        pass
    return json.dumps({"error": "Instance not found"})


@mcp.resource("browser://{instance_id}/cookies")
async def get_cookies_resource(instance_id: str) -> str:
    """
    Get cookies for a browser instance as a resource.

    Args:
        instance_id: Browser instance ID.

    Returns:
        JSON string of cookies.
    """
    try:
        cookies = await browser_manager.get_cookies(instance_id)
        return json.dumps(cookies, indent=2, default=str)
    except Exception:
        return json.dumps({"error": "Instance not found"})


# ===========================================================================
# DISABLED SECTIONS
#
# The following tool sections require direct CDP/nodriver access and are NOT
# available in cloud browser mode. They are listed here for documentation.
#
# If you need similar functionality, use execute_script() to run JavaScript
# in the page context, which covers most use cases.
#
# Disabled sections:
#   - network-debugging: list_network_requests, get_request_details,
#       get_response_details, get_response_content, modify_headers
#       (Reason: requires CDP Network domain interception)
#
#   - cdp-functions: execute_cdp_command, get_execution_contexts,
#       discover_global_functions, discover_object_methods,
#       call_javascript_function, inspect_function_signature,
#       inject_and_execute_script, create_persistent_function,
#       execute_function_sequence, create_python_binding,
#       execute_python_in_browser, get_function_executor_info,
#       list_cdp_commands
#       (Reason: requires direct CDP protocol access)
#
#   - element-extraction: extract_element_styles, extract_element_structure,
#       extract_element_events, extract_element_animations,
#       extract_element_assets, extract_element_styles_cdp,
#       extract_related_files, clone_element_complete,
#       extract_complete_element_cdp
#       (Reason: requires CDP DOM/CSS domain. Use execute_script instead.)
#
#   - progressive-cloning: clone_element_progressive, expand_styles,
#       expand_events, expand_children, expand_css_rules,
#       expand_pseudo_elements, expand_animations, list_stored_elements,
#       clear_stored_element, clear_all_elements
#       (Reason: requires CDP + local element storage)
#
#   - file-extraction: clone_element_to_file, extract_complete_element_to_file,
#       extract_element_styles_to_file, extract_element_structure_to_file,
#       extract_element_events_to_file, extract_element_animations_to_file,
#       extract_element_assets_to_file, list_clone_files, cleanup_clone_files
#       (Reason: requires CDP + local filesystem)
#
#   - dynamic-hooks: create_dynamic_hook, create_simple_dynamic_hook,
#       list_dynamic_hooks, get_dynamic_hook_details, remove_dynamic_hook,
#       get_hook_documentation, get_hook_examples,
#       get_hook_requirements_documentation, get_hook_common_patterns,
#       validate_hook_function
#       (Reason: requires CDP Fetch domain interception)
#
#   - tabs: list_tabs, switch_tab, close_tab, get_active_tab, new_tab
#       (Reason: cloud browser is single-tab per session)
#
# ===========================================================================


# ===========================================================================
# Entry Point
# ===========================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="browser.proxies.sx MCP Server - Cloud antidetect browser automation"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", 8000)),
        help="Port for HTTP transport",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP transport",
    )

    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
