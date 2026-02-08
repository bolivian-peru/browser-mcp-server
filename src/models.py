"""Data models for browser.proxies.sx MCP server."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class BrowserState(str, Enum):
    """Browser instance states."""
    STARTING = "starting"
    READY = "ready"
    NAVIGATING = "navigating"
    ERROR = "error"
    CLOSED = "closed"


class BrowserInstance(BaseModel):
    """Represents a browser instance."""
    instance_id: str = Field(description="Unique identifier for the browser instance")
    state: BrowserState = Field(default=BrowserState.STARTING)
    current_url: Optional[str] = Field(default=None, description="Current page URL")
    title: Optional[str] = Field(default=None, description="Current page title")
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    headless: bool = Field(default=True)
    user_agent: Optional[str] = None
    viewport: Dict[str, int] = Field(default_factory=lambda: {"width": 1920, "height": 1080})

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()


class ElementInfo(BaseModel):
    """Information about a DOM element."""
    selector: str = Field(description="CSS selector or XPath")
    tag_name: str = Field(description="HTML tag name")
    text: Optional[str] = Field(default=None, description="Element text content")
    attributes: Dict[str, str] = Field(default_factory=dict)
    is_visible: bool = Field(default=True)
    is_clickable: bool = Field(default=False)
    bounding_box: Optional[Dict[str, float]] = None
    children_count: int = Field(default=0)


class PageState(BaseModel):
    """Complete state snapshot of a page."""
    instance_id: str
    url: str
    title: str
    ready_state: str = Field(default="complete", description="Document ready state")
    cookies: List[Dict[str, Any]] = Field(default_factory=list)
    local_storage: Dict[str, str] = Field(default_factory=dict)
    session_storage: Dict[str, str] = Field(default_factory=dict)
    console_logs: List[Dict[str, Any]] = Field(default_factory=list)
    viewport: Dict[str, int] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class BrowserOptions(BaseModel):
    """Options for spawning a new cloud browser instance via browser.proxies.sx."""
    # Cloud browser options
    country: Optional[str] = Field(
        default=None,
        description="Proxy country code: US, GB, DE, FR, ES, PL"
    )
    duration_minutes: Optional[int] = Field(
        default=60,
        description="Session duration in minutes (15-480). Pricing: $0.005/min ($0.30/hr)"
    )
    profile_id: Optional[str] = Field(
        default=None,
        description="Identity Bundle ID to load (restores cookies, localStorage, fingerprint)"
    )
    payment_signature: Optional[str] = Field(
        default=None,
        description="x402 USDC payment transaction hash (Base or Solana)"
    )

    # Kept for compatibility but note: cloud browser is always headless
    user_agent: Optional[str] = Field(default=None, description="Custom user agent string (optional override)")
    viewport_width: int = Field(default=1920, description="Viewport width in pixels")
    viewport_height: int = Field(default=1080, description="Viewport height in pixels")


class NavigationOptions(BaseModel):
    """Options for page navigation."""
    wait_until: str = Field(default="domcontentloaded", description="Wait condition: load, domcontentloaded, networkidle")
    timeout: int = Field(default=30000, description="Navigation timeout in milliseconds")
    referrer: Optional[str] = Field(default=None, description="Referrer URL")


class ScriptResult(BaseModel):
    """Result from script execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time: float = Field(default=0, description="Execution time in milliseconds")
