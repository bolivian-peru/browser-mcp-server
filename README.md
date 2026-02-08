# browser.proxies.sx MCP Server

Cloud antidetect browser automation via [browser.proxies.sx](https://browser.proxies.sx) HTTP API.

> Fork of [vibheksoni/stealth-browser-mcp](https://github.com/vibheksoni/stealth-browser-mcp) — adapted from local nodriver/CDP to cloud browser sessions with auto-allocated mobile proxies.

## What This Does

Gives any MCP-compatible AI agent (Claude, Cursor, Windsurf, etc.) access to cloud antidetect browser sessions that include:

- **Camoufox antidetect fingerprint** — unique per session
- **Auto-allocated 4G/5G mobile proxy** — 6 countries (US, GB, DE, FR, ES, PL)
- **Identity Bundles v1.1.0** — save/restore cookies, localStorage, fingerprint, proxy binding across sessions
- **x402 USDC micropayments** — pay per minute on Base or Solana

No local Chrome/Chromium needed. Everything runs in the cloud.

**Pricing:** $0.005/min ($0.30/hr) — single flat rate.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/bolivian-peru/browser-mcp-server.git
cd browser-mcp-server

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your internal key (or use x402 payment)
export BROWSER_INTERNAL_KEY=your_key_here
```

### Add to Claude Code

```bash
claude mcp add-json browser-proxies-sx '{
  "type": "stdio",
  "command": "/path/to/browser-mcp-server/venv/bin/python",
  "args": ["/path/to/browser-mcp-server/src/server.py"],
  "env": {
    "BROWSER_INTERNAL_KEY": "your_key_here"
  }
}'
```

### Manual MCP Config

```json
{
  "mcpServers": {
    "browser-proxies-sx": {
      "command": "/path/to/browser-mcp-server/venv/bin/python",
      "args": ["/path/to/browser-mcp-server/src/server.py"],
      "env": {
        "BROWSER_INTERNAL_KEY": "your_key_here"
      }
    }
  }
}
```

### HTTP Transport

```bash
python src/server.py --transport http --port 8000
```

## Tools (30)

### Browser Management (4)

| Tool | Description |
|------|-------------|
| `spawn_browser` | Create cloud antidetect session (country, duration, profile, payment) |
| `list_instances` | List all active browser sessions |
| `close_instance` | Close a browser session |
| `get_instance_state` | Get page state (URL, title, cookies, viewport) |

### Navigation (4)

| Tool | Description |
|------|-------------|
| `navigate` | Navigate to a URL |
| `go_back` | Browser history back |
| `go_forward` | Browser history forward |
| `reload_page` | Reload current page |

### Element Interaction (7)

| Tool | Description |
|------|-------------|
| `click_element` | Click element by CSS selector |
| `type_text` | Type text with human-like delay |
| `paste_text` | Instant text paste (no delay) |
| `press_key` | Press keyboard key (Enter, Tab, etc.) |
| `select_option` | Select dropdown option (by value, text, or index) |
| `wait_for_element` | Wait for element to appear |
| `scroll_page` | Scroll (up, down, left, right, top, bottom) |

### Page Content (6)

| Tool | Description |
|------|-------------|
| `query_elements` | Query DOM elements by selector |
| `get_element_state` | Get element attributes, styles, position |
| `get_page_content` | Get page HTML content |
| `get_page_text` | Get text content of page or element |
| `take_screenshot` | Take screenshot (viewport or full page) |
| `execute_script` | Execute JavaScript in page context |

### Cookies & Storage (5)

| Tool | Description |
|------|-------------|
| `get_cookies` | Get all cookies |
| `set_cookie` | Set a cookie |
| `clear_cookies` | Clear all cookies |
| `get_local_storage` | Get localStorage data |
| `set_local_storage` | Set localStorage items |

### Identity Bundles (4)

| Tool | Description |
|------|-------------|
| `save_profile` | Save session as Identity Bundle (cookies + localStorage + fingerprint + proxy binding) |
| `load_profile` | Load Identity Bundle into current session |
| `list_profiles` | List all saved profiles |
| `delete_profile` | Delete a saved profile |

## Authentication

Two options:

### 1. Internal Key (for testing/internal use)
```bash
export BROWSER_INTERNAL_KEY=your_key_here
```

### 2. x402 USDC Payment (for production)

Call `spawn_browser()` without a payment signature. The server returns a 402 response with wallet addresses:

```
Base:   0xF8cD900794245fc36CBE65be9afc23CDF5103042
Solana: 6eUdVwsPArTxwVqEARYGCh4S2qwW2zCs7jSEDRpxydnv
```

Send the exact USDC amount, then call `spawn_browser(payment_signature="tx_hash")`.

## Identity Bundles

Save and restore complete browser identity across sessions:

```
1. spawn_browser(country="US")           # Create session
2. navigate(id, "https://example.com")   # Do your browsing
3. save_profile(id, name="my-session")   # Save everything
4. close_instance(id)                     # Close session

# Later...
5. spawn_browser(profile_id="prof_xxx")  # Restore exact identity
```

What gets saved:
- All cookies
- localStorage data
- Browser fingerprint
- Proxy device binding (same IMEI = same IP)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BROWSER_API_URL` | Browser API base URL | `https://browser.proxies.sx` |
| `BROWSER_INTERNAL_KEY` | Internal authentication key | (none) |
| `PAYMENT_SIGNATURE` | Default x402 payment tx hash | (none) |

## Differences from Original

This fork replaces the original's local nodriver/CDP approach with cloud browser sessions via HTTP API:

| Feature | Original (stealth-browser-mcp) | This Fork |
|---------|-------------------------------|-----------|
| Browser | Local Chrome via nodriver | Cloud Camoufox via API |
| Proxy | None (bring your own) | Auto-allocated 4G/5G mobile |
| Fingerprint | nodriver stealth | Camoufox antidetect |
| Identity Bundles | None | Full profile save/restore |
| Payment | Free | x402 USDC micropayments |
| Tools | 90 (CDP-dependent) | 30 (cloud-compatible) |
| Setup | Install Chrome locally | No local browser needed |

### Disabled Sections

The following original tool sections require direct CDP access and are not available in cloud mode:

- **Network debugging** — CDP Network domain interception
- **CDP functions** — Direct Chrome DevTools Protocol commands
- **Element extraction** — CDP DOM/CSS domain queries
- **Progressive cloning** — CDP + local element storage
- **File extraction** — CDP + local filesystem
- **Dynamic hooks** — CDP Fetch domain interception
- **Tabs** — Cloud browser is single-tab per session

Most of these use cases can be handled via `execute_script()` for JavaScript-based alternatives.

## Links

- **API:** https://browser.proxies.sx
- **Main repo:** https://github.com/bolivian-peru/browser-proxies-sx
- **MCP (TypeScript):** https://github.com/bolivian-peru/browser-mcp
- **Original:** https://github.com/vibheksoni/stealth-browser-mcp
- **Proxies.sx:** https://agents.proxies.sx

## License

MIT — see [LICENSE](LICENSE).
