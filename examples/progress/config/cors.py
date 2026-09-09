"""CORS — which origins may call this application from a browser.

Paths that do not match `paths` are left alone, so a public marketing page
does not sprout `Access-Control-Allow-Origin`. Defaults match Laravel's
`config/cors.php`.
"""

config = {
    "paths": ["api/*", "signet/csrf-cookie"],
    "allowed_methods": ["*"],
    "allowed_origins": ["*"],
    "allowed_origins_patterns": [],
    "allowed_headers": ["*"],
    "exposed_headers": [],
    "max_age": 0,
    "supports_credentials": False,
}
