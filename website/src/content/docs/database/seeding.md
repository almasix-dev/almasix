---
title: Seeding
description: Seed your database with test data using Almasix seeders.
---

Almasix includes a simple method of seeding your database with test data using seed classes. All seeders live in `database/seeders`.

:::tip
[Model factories](/database/factories/) are the usual source of seed rows:
`await User.factory().count(10).create()`.
:::


## Writing seeders

```
database/
  seeders/
    __init__.py
    database_seeder.py   # DatabaseSeeder — default entry point
    user_seeder.py
```

`almasix new` ships an empty `DatabaseSeeder`. Override `run` and call child seeders:

```python
# database/seeders/database_seeder.py
from almasix.orm import Seeder
from database.seeders.user_seeder import UserSeeder

class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await self.call([UserSeeder])
        # await self.call_once(UserSeeder)
        # await self.call_with(UserSeeder, {"count": 10})
        # await self.call_silent([UserSeeder])
```

```python
# database/seeders/user_seeder.py
class UserSeeder(Seeder):
    async def run(self, count: int = 1) -> None:
        from app.models.user import User

        for i in range(count):
            await User.create(email=f"u{i}@example.com", name=f"User {i}")
```

## Seeding with factories

Writing rows out by hand gets old at the third one. A
[factory](/database/factories/) describes the row once and a seeder asks for
as many as it wants, pinning only the columns that matter:

```python
# database/seeders/demo_seeder.py
from almasix.orm import Seeder

from app.models.post import Post
from app.models.user import User


class DemoSeeder(Seeder):
    async def run(self) -> None:
        ada = await User.factory().create({"email": "ada@almasix.dev", "name": "Ada"})
        await Post.factory().count(3).for_(ada, "author").create()
        await User.factory().count(10).has(Post.factory().count(2), "posts").create()
```

## Suppressing model events

```python
# database/seeders/quiet_seeder.py
from almasix.orm import Seeder, WithoutModelEvents

class QuietSeeder(WithoutModelEvents, Seeder):
    async def run(self) -> None:
        await User.create(email="quiet@example.com", name="Quiet")
```

You may also wrap a block with `without_model_events()`.

## Running seeders

```bash
python smith make:seeder UserSeeder
python smith db:seed
python smith db:seed --class UserSeeder
python smith migrate --seed
python smith migrate --seed --seeder UserSeeder
python smith migrate:fresh --seed
```

`--seeder` implies seeding (you may omit `--seed` when `--seeder` is set). The default class is `DatabaseSeeder`.
