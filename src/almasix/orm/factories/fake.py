"""Fake data — Laravel's `fake()` helper, without the Faker dependency.

Laravel binds `Faker\\Generator` in the container and factories reach it as
`$this->faker`. Almasix ships the providers factory definitions actually use
and lets an application swap in the real `faker` package with
`Fake.resolve_using(...)` when it wants the other thousand.
"""

from __future__ import annotations

import random
import re
import string
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls
from datetime import time as time_cls
from typing import Any

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")

FIRST_NAMES = (
    "Ada", "Grace", "Alan", "Linus", "Barbara", "Ken", "Margaret", "Dennis",
    "Radia", "Guido", "Katherine", "Tim", "Anita", "Bjarne", "Shafi", "Vint",
    "Frances", "Donald", "Hedy", "Edsger", "Sophie", "Amara", "Juma", "Zawadi",
)
LAST_NAMES = (
    "Lovelace", "Hopper", "Turing", "Torvalds", "Liskov", "Thompson", "Hamilton",
    "Ritchie", "Perlman", "Rossum", "Johnson", "Berners-Lee", "Borg", "Stroustrup",
    "Goldwasser", "Cerf", "Allen", "Knuth", "Lamarr", "Dijkstra", "Wilson", "Okoro",
)
WORDS = (
    "alias", "amet", "aperiam", "aspernatur", "beatae", "commodi", "consequatur",
    "cumque", "dolor", "dolorem", "eius", "enim", "error", "esse", "et", "eum",
    "fuga", "harum", "id", "illum", "impedit", "ipsa", "iste", "labore", "magni",
    "modi", "molestiae", "nemo", "nihil", "nobis", "odio", "officia", "omnis",
    "porro", "quaerat", "quasi", "quia", "quo", "ratione", "rerum", "saepe",
    "sequi", "sint", "sit", "tempora", "ullam", "unde", "vel", "veritatis", "vitae",
)
CITIES = (
    "Nairobi", "Mombasa", "Kisumu", "Arusha", "Kampala", "Kigali", "Dar es Salaam",
    "Lisbon", "Porto", "Utrecht", "Helsinki", "Kyoto", "Valparaíso", "Reykjavík",
)
COUNTRIES = (
    ("Kenya", "KE"), ("Tanzania", "TZ"), ("Uganda", "UG"), ("Rwanda", "RW"),
    ("Portugal", "PT"), ("Netherlands", "NL"), ("Finland", "FI"), ("Japan", "JP"),
    ("Chile", "CL"), ("Iceland", "IS"), ("Canada", "CA"), ("Kazakhstan", "KZ"),
)
STREETS = (
    "Acacia", "Baobab", "Cedar", "Dhow", "Elgon", "Forest", "Gemstone", "Harbour",
    "Ironwood", "Jacaranda", "Kilimanjaro", "Limestone", "Mango", "Nile",
)
STREET_SUFFIXES = ("Avenue", "Road", "Street", "Lane", "Close", "Crescent", "Way")
COMPANY_SUFFIXES = ("Ltd", "Group", "Labs", "Works", "Collective", "Partners", "PLC")
FREE_DOMAINS = ("gmail.com", "outlook.com", "proton.me", "yahoo.com")
TLDS = ("com", "dev", "io", "org", "net", "africa")
CURRENCIES = ("KES", "TZS", "UGX", "EUR", "USD", "GBP", "JPY", "ZAR")


class FakeUniquenessError(RuntimeError):
    """A unique provider ran out of room before it found a fresh value."""


class UniqueFake:
    """`fake.unique().email()` — retries until the value has not been used."""

    def __init__(self, source: Fake, retries: int = 100) -> None:
        self._source = source
        self._retries = retries

    def __getattr__(self, name: str) -> Callable[..., Any]:
        provider = getattr(self._source, name)

        def unique(*args: Any, **kwargs: Any) -> Any:
            seen = self._source._seen.setdefault(name, set())
            for _ in range(self._retries):
                value = provider(*args, **kwargs)
                if value not in seen:
                    seen.add(value)
                    return value
            raise FakeUniquenessError(
                f"fake.unique().{name}() found no fresh value in {self._retries} tries"
            )

        return unique


class Fake:
    """The providers a factory definition reaches for.

    Every value comes from one seedable `random.Random`, so a seeded run of a
    seeder or a test produces the same database twice.
    """

    #: Replaced by `Fake.resolve_using` — how `Factory.fake` is built.
    _resolver: Callable[[], Any] | None = None

    def __init__(self, seed: int | None = None) -> None:
        self.random = random.Random(seed)
        self._seen: dict[str, set[Any]] = {}

    # --- plumbing -----------------------------------------------------------

    def seed(self, value: int | None) -> Fake:
        """Reset the underlying stream — the same seed replays the same data."""
        self.random.seed(value)
        return self

    def unique(self, retries: int = 100) -> UniqueFake:
        return UniqueFake(self, retries)

    def reset_unique(self) -> Fake:
        self._seen.clear()
        return self

    @classmethod
    def resolve_using(cls, resolver: Callable[[], Any] | None) -> None:
        """Swap the generator factories get — e.g. the `faker` package.

            Fake.resolve_using(lambda: faker.Faker("sw_KE"))
        """
        cls._resolver = resolver

    @classmethod
    def resolve(cls) -> Any:
        return cls._resolver() if cls._resolver is not None else cls()

    def __getattr__(self, name: str) -> Any:
        """Accept Laravel's camelCase spellings — `fake.safeEmail()`."""
        snake = _CAMEL.sub("_", name).lower()
        if snake != name:
            return getattr(self, snake)
        raise AttributeError(f"{type(self).__name__} has no provider {name!r}")

    # --- primitives ---------------------------------------------------------

    def random_int(self, minimum: int = 0, maximum: int = 9999) -> int:
        return self.random.randint(minimum, maximum)

    def number_between(self, minimum: int = 0, maximum: int = 9999) -> int:
        return self.random_int(minimum, maximum)

    def random_digit(self) -> int:
        return self.random.randint(0, 9)

    def random_number(self, digits: int = 5) -> int:
        return self.random.randint(10 ** (digits - 1), 10**digits - 1)

    def random_float(self, minimum: float = 0.0, maximum: float = 1000.0, ndigits: int = 2) -> float:
        return round(self.random.uniform(minimum, maximum), ndigits)

    def random_element(self, elements: Sequence[Any]) -> Any:
        return self.random.choice(list(elements))

    def random_elements(
        self,
        elements: Sequence[Any],
        count: int = 1,
        unique: bool = False,
    ) -> list[Any]:
        pool = list(elements)
        if unique:
            return self.random.sample(pool, k=min(count, len(pool)))
        return [self.random.choice(pool) for _ in range(count)]

    def shuffle(self, elements: Sequence[Any]) -> list[Any]:
        pool = list(elements)
        self.random.shuffle(pool)
        return pool

    def boolean(self, chance_of_true: int = 50) -> bool:
        return self.random.randint(1, 100) <= chance_of_true

    def uuid(self) -> str:
        return str(uuid.UUID(int=self.random.getrandbits(128), version=4))

    def password(self, length: int = 12) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(self.random.choice(alphabet) for _ in range(length))

    def hex_color(self) -> str:
        return f"#{self.random.randrange(0x1000000):06x}"

    def currency_code(self) -> str:
        return self.random_element(CURRENCIES)

    # --- people -------------------------------------------------------------

    def first_name(self) -> str:
        return self.random_element(FIRST_NAMES)

    def last_name(self) -> str:
        return self.random_element(LAST_NAMES)

    def name(self) -> str:
        return f"{self.first_name()} {self.last_name()}"

    def user_name(self) -> str:
        return f"{self.first_name().lower()}.{self.last_name().lower()}".replace(" ", "")

    def job_title(self) -> str:
        return f"{self.word().title()} {self.random_element(('Engineer', 'Lead', 'Analyst'))}"

    # --- internet -----------------------------------------------------------

    def domain_name(self) -> str:
        return f"{self.word()}{self.random_int(1, 99)}.{self.random_element(TLDS)}"

    def free_email(self) -> str:
        return f"{self.user_name()}@{self.random_element(FREE_DOMAINS)}"

    def safe_email(self) -> str:
        return f"{self.user_name()}{self.random_int(1, 9999)}@example.com"

    def email(self) -> str:
        return f"{self.user_name()}{self.random_int(1, 9999)}@{self.domain_name()}"

    def url(self) -> str:
        return f"https://{self.domain_name()}/{self.slug(3)}"

    def slug(self, words: int = 4) -> str:
        return "-".join(self.random_elements(WORDS, words))

    def ipv4(self) -> str:
        return ".".join(str(self.random_int(1, 254)) for _ in range(4))

    # --- text ---------------------------------------------------------------

    def word(self) -> str:
        return self.random_element(WORDS)

    def words(self, count: int = 3, as_text: bool = False) -> list[str] | str:
        chosen = self.random_elements(WORDS, count)
        return " ".join(chosen) if as_text else chosen

    def sentence(self, words: int = 6) -> str:
        body = " ".join(self.random_elements(WORDS, max(1, words)))
        return f"{body[0].upper()}{body[1:]}."

    def sentences(self, count: int = 3, as_text: bool = False) -> list[str] | str:
        chosen = [self.sentence() for _ in range(count)]
        return " ".join(chosen) if as_text else chosen

    def paragraph(self, sentences: int = 3) -> str:
        return " ".join(self.sentence() for _ in range(sentences))

    def paragraphs(self, count: int = 3, as_text: bool = False) -> list[str] | str:
        chosen = [self.paragraph() for _ in range(count)]
        return "\n\n".join(chosen) if as_text else chosen

    def text(self, max_chars: int = 200) -> str:
        body = ""
        while len(body) < max_chars:
            body = f"{body} {self.sentence()}".strip()
        return body[: max_chars - 1].rstrip(" ,.") + "."

    def title(self) -> str:
        return " ".join(word.title() for word in self.random_elements(WORDS, 4))

    # --- places -------------------------------------------------------------

    def city(self) -> str:
        return self.random_element(CITIES)

    def country(self) -> str:
        return self.random_element(COUNTRIES)[0]

    def country_code(self) -> str:
        return self.random_element(COUNTRIES)[1]

    def street_address(self) -> str:
        street = self.random_element(STREETS)
        return f"{self.random_int(1, 400)} {street} {self.random_element(STREET_SUFFIXES)}"

    def postcode(self) -> str:
        return f"{self.random_int(10000, 99999)}"

    def address(self) -> str:
        return f"{self.street_address()}, {self.city()} {self.postcode()}"

    def phone_number(self) -> str:
        return f"+254 7{self.random_int(10, 99)} {self.random_int(100, 999)} {self.random_int(100, 999)}"

    def company(self) -> str:
        return f"{self.last_name()} {self.random_element(COMPANY_SUFFIXES)}"

    # --- time ---------------------------------------------------------------

    def date_time_between(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> datetime:
        now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
        start = start or now - timedelta(days=365)
        end = end or now
        span = int((end - start).total_seconds())
        return start + timedelta(seconds=self.random_int(0, max(0, span)))

    def date_time(self) -> datetime:
        return self.date_time_between()

    def date_time_this_month(self) -> datetime:
        now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
        return self.date_time_between(now.replace(day=1), now)

    def date(self) -> date_cls:
        return self.date_time().date()

    def time(self) -> time_cls:
        return self.date_time().time()


#: The process-wide generator, the way Laravel's `fake()` helper is one call.
fake = Fake()
