---
title: Hashing
description: Hash.make / check / needs_rehash — bcrypt default, optional argon2id.
---

Almasix’s `Hash` façade hashes and verifies passwords (bcrypt by default).

```python
# examples/hashing.py
from almasix.hashing import Hash

hashed = Hash.make("secret")
Hash.check("secret", hashed)
Hash.needs_rehash(hashed)
Hash.is_hashed(hashed)
```

## Drivers

| Driver | Config | Notes |
| --- | --- | --- |
| `bcrypt` (default) | `hashing.bcrypt.rounds` | Bundled (`bcrypt` package) |
| `argon2` / `argon2id` | `hashing.argon2.{memory,threads,time}` | Optional: `pip install 'almasix[argon2]'` |

```python
# config/hashing.py
config = {
    "driver": "bcrypt",
    "bcrypt": {"rounds": 12},
    "argon2": {"memory": 65536, "threads": 1, "time": 4},
}
```

```python
# examples/hashing.py
Hash.driver("argon2id").make("secret")
```

On successful session login, Almasix rehashes when `needs_rehash` is true
(work-factor / algorithm drift).

## Related

- [Authentication](/authentication/)
- [Passwords](/passwords/)
