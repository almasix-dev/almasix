---
title: Passwords
description: Password broker, confirmation middleware, and reset tokens.
---

## Password confirmation

Routes that need a fresh password check use `password.confirm`. After the user
re-enters their password, call `mark_password_confirmed(request)`. Timeout comes
from `auth.password_timeout` (default 3 hours).

## Reset broker

```python title="app/http/controllers/auth_controller.py"
from almasix.auth import Password
from almasix.hashing import Hash

status = await Password.send_reset_link({"email": email})
# Password.RESET_LINK_SENT | INVALID_USER | RESET_THROTTLED

status = await Password.reset(
    {"email": email, "token": token, "password": new_password},
    lambda user, password: _apply(user, password),
)
```

Statuses map through `lang/en/passwords.py` via `Password.status_message(status)`.

Delivery uses notifications by default (`ResetPasswordNotification` via mail).
Override with `Password.create_url_using(callback)` when you need a custom path:

```python title="app/providers/app_service_provider.py"
from almasix.auth.passwords import get_password_manager

get_password_manager().create_url_using(lambda user, token: log_or_queue(user, token))
```

Tokens live in an in-memory repository by default. Set
`auth.passwords.users.use_database = True` (and migrate a
`password_reset_tokens` table with `email` / `token` / `created_at`) to persist
them.

Successful resets dispatch a `PasswordReset` auth event.

## Related

- [Authentication](/authentication/)
- [Hashing](/hashing/)
- [Notifications](/notifications/)
- [Mail](/mail/)
