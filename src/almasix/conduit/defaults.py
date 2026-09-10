"""Default Conduit configuration (merged as ``conduit``)."""

config = {
    "endpoint": "/conduit/update",
    "asset_url": "/conduit/conduit.js",
    "inject_assets": True,
    "checksum_key": None,
    "alpine_cdn": "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js",
    "csp_safe": False,
    "alpine_csp_cdn": "https://cdn.jsdelivr.net/npm/@alpinejs/csp@3.x.x/dist/cdn.min.js",
    "coalesce_ms": 16,
    "signature_ttl_minutes": 720,
    "signed_updates": True,
}
