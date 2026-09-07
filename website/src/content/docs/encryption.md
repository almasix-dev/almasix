---
title: Encryption
description: Crypt.encrypt / decrypt — JSON-safe payloads, APP_KEY, and key rotation.
---

## Introduction

Avalon encrypts values with an authenticated stream cipher keyed by `APP_KEY`.
Encrypted payloads are MAC-signed so tampering fails closed. Cookie encryption
(M7) and the app-facing `Crypt` façade share the same cipher.

```python
from avalon.encryption import Crypt, DecryptException, encrypt, decrypt

encrypted = Crypt.encrypt({"token": "secret"})
Crypt.decrypt(encrypted)

Crypt.encrypt_string("raw text")
Crypt.decrypt_string(encrypted_string)
```

Helpers `encrypt` / `decrypt` / `encrypt_string` / `decrypt_string` mirror the façade.

## Configuration

```python
# config/app.py
"key": env("APP_KEY", "base64:local-dev-key-change-me"),
"previous_keys": env("APP_PREVIOUS_KEYS", ""),
```

| Variable | Purpose |
| --- | --- |
| `APP_KEY` | Current encryption key (set with `grail key:generate`) |
| `APP_PREVIOUS_KEYS` | Comma-separated prior keys for graceful rotation |

Generate a key:

```bash
grail key:generate
```

## JSON-safe encrypt

`Crypt.encrypt` / `decrypt` serialize with **JSON** (not pickle). Pass dicts,
lists, strings, numbers, booleans, or `null`. Non-JSON-safe objects raise
`EncryptException` — use `encrypt_string` for raw text instead.

```python
from avalon.encryption import EncryptException

try:
    Crypt.encrypt(object())  # not JSON-serializable
except EncryptException:
    ...
```

## Decrypting and tamper detection

If the MAC is invalid or no key can open the payload, Avalon raises
`DecryptException`:

```python
from avalon.encryption import Crypt, DecryptException

try:
    Crypt.decrypt(tampered)
except DecryptException:
    ...
```

## Rotating keys

Encrypt always uses the current `APP_KEY`. Decrypt tries the current key, then
each entry in `APP_PREVIOUS_KEYS` until one succeeds:

```ini
APP_KEY="base64:new-key…"
APP_PREVIOUS_KEYS="base64:old-key-a…,base64:old-key-b…"
```

Sessions and encrypted cookies stay readable across a rotation when previous
keys are listed.

## Cookie encryption

`EncryptCookies` middleware uses the same keying story (current + previous keys)
so rotating `APP_KEY` does not immediately invalidate encrypted cookies.
