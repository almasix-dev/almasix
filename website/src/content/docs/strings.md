---
title: Strings
description: Str and the fluent Stringable — every string helper, documented method by method.
---

Almasix has two ways to work a string. `Str` is a namespace of static methods
that take the subject as their first argument, and `str_()` wraps a string in a
`Stringable` so the same operations chain:

```python title="app/http/controllers/post_controller.py"
from almasix.support import Str, str_

Str.slug(Str.title("the hitchhiker's guide"))
# 'the-hitchhikers-guide'

str_("the hitchhiker's guide").title().slug().value()
# 'the-hitchhikers-guide'
```

Every `Str` method is available fluently: `Stringable` delegates the whole
static surface rather than hand-picking a subset, so anything on this page's
first half can be called on the second half's receiver. Methods also accept
camelCase aliases — `Str.doesntStartWith` for `Str.doesnt_start_with`,
`beforeLast('/')` for `before_last('/')`. The snake_case name is the
documented one.

`Stringable` is immutable. Each fluent call returns a new instance, and the
receiver is unchanged:

```python title="examples/strings.py"
name = str_("ada lovelace")
upper = name.upper()

(str(name), str(upper))
# ('ada lovelace', 'ADA LOVELACE')
```

Reach for the string itself with `value()`, `to_string()`, or `str(...)`; a
`Stringable` also compares equal to the string it holds, so most code can pass
it straight to something expecting `str`.

## Not included

A few fluent methods have no counterpart here, and are absent rather than
faked:

| Method | Why it is absent |
| --- | --- |
| `scan` | PHP-style `sscanf` format strings; Python's parsing story is different enough that adding it would be a new API |
| `toHtmlString` | Prism's escaper honours `__html__`, so `HtmlString` from `almasix.prism` is the equivalent — see [Views](/views/) |
| `toUri` | Prefer `url()` / named routes — see [URL Generation](/urls/) |

## Strings

Static methods on `Str`. Each takes the subject as its first argument and
returns a plain value.

### after

Returns everything after the first occurrence of `search`. If `search` is not
in the subject, or is the empty string, the whole subject comes back unchanged
rather than an empty string.

```python title="resources/views/examples/strings.prism.html"
from almasix.support import Str

result = Str.after("ada@example.com", "@")

# 'example.com'

missing = Str.after("ada", "@")

# 'ada'
```

### after_last

Returns everything after the last occurrence of `search`, which is what you
want for the final segment of a path or a namespace. A `search` that is absent
or empty returns the subject unchanged.

```python title="app/models/example.py"
result = Str.after_last("app/Models/User.py", "/")

# 'User.py'
```

### apa

Capitalises a title in approximate APA style: every word is capitalised except
a fixed set of short joining words (`a`, `an`, `and`, `as`, `at`, `but`, `by`,
`for`, `in`, `nor`, `of`, `on`, `or`, `so`, `the`, `to`, `up`, `yet`), and the
first and last words are always capitalised whatever they are.

```python title="examples/strings.py"
result = Str.apa("a nice title for the almasix docs")

# 'A Nice Title for the Almasix Docs'

kept = Str.apa("A TALE of two cities")

# 'A TALE of Two Cities'
```

Only the first letter is touched, so a word that is already in capitals keeps
them. The implementation is an approximation of APA style: the small-word list
is the fixed set above, and hyphenated words are not handled specially.

### ascii

Transliterates a string to ASCII by decomposing it (Unicode NFKD) and dropping
every character that has no ASCII form. Accented Latin letters survive as their
base letter.

```python title="examples/strings.py"
result = Str.ascii("Crème brûlée")

# 'Creme brulee'
```

Characters that do not decompose to an ASCII letter are removed, not mapped:
`Str.ascii("Kjøbenhavn")` is `'Kjbenhavn'` and a Cyrillic string comes back
empty — there is no separate transliteration table that would map `ø` to `o`.
`Str.transliterate` is an alias for the same function.

### before

Returns everything before the first occurrence of `search`. An absent or empty
`search` returns the subject unchanged.

```python title="resources/views/examples/strings.prism.html"
result = Str.before("ada@example.com", "@")

# 'ada'
```

### before_last

Returns everything before the last occurrence of `search` — the directory part
of a path, for instance.

```python title="app/models/example.py"
result = Str.before_last("app/Models/User.py", "/")

# 'app/Models'
```

### between

Returns the portion between `from_` and `to`: everything after the first
`from_`, up to the first `to` that follows it. `from_` is spelled with a
trailing underscore because `from` is a Python keyword. If either delimiter is
empty the subject comes back unchanged.

```python title="examples/strings.py"
result = Str.between("The [quick] brown [fox]", "[", "]")

# 'quick'

smallest = Str.between("[a] bc [d]", "[", "]")

# 'a'
```

Almasix stops at the *first* occurrence of `to` after `from_` (so the
second example yields `'a'`), which matches `between_first`.

### between_first

Returns the smallest portion between `from_` and `to`. In Almasix this is an
alias — it calls `between`, which already stops at the first `to`, so the two
methods always return the same string.

```python title="examples/strings.py"
result = Str.between_first("[a] bc [d]", "[", "]")

# 'a'
```

### camel

Converts a string to camelCase. The value is split on every run of
non-alphanumeric characters, each part is capitalised, and the first letter is
lower-cased.

```python title="examples/strings.py"
result = Str.camel("foo_bar")

# 'fooBar'

spaced = Str.camel("user profile id")

# 'userProfileId'
```

Splitting happens on separators only, not on case boundaries, so an existing
capital inside a part is left alone.

### char_at

Returns the single character at `index`, or `False` when the index is outside
the string. It returns a `bool` rather than raising `IndexError`, so test the
result before using it.

```python title="examples/strings.py"
result = Str.char_at("Ada", 1)

# 'd'

out_of_range = Str.char_at("Ada", 9)

# False
```

A negative index counts back from the end, as with Python slicing,
and still returns `False` when it reaches past the start.

```python title="examples/strings.py"
last = Str.char_at("Ada", -1)

# 'a'
```

### chop_end

Removes `needle` from the end of the subject if it is there, and returns the
subject untouched otherwise. Pass an iterable to try several suffixes; the
first one in the iterable that matches is the one removed, and only one is
removed per call.

```python title="app/models/example.py"
result = Str.chop_end("app/Models/User.py", ".py")

# 'app/Models/User'

extensions = Str.chop_end("image.jpeg", [".jpg", ".jpeg"])

# 'image'
```

### chop_start

Removes `needle` from the start of the subject if it is there. As with
`chop_end`, an iterable is tried in order and only the first match is removed,
so put the longer prefix first when one is a prefix of the other.

```python title="examples/strings.py"
result = Str.chop_start("https://example.com", ["https://", "http://"])

# 'example.com'

path = Str.chop_start("/users/1", "/")

# 'users/1'
```

### contains

Whether the haystack contains any of the needles. `needles` is a single string
or an iterable of them, and `ignore_case` compares both sides in lower case. An
empty needle never matches.

```python title="examples/strings.py"
result = Str.contains("Ada Lovelace", "Love")

# True

insensitive = Str.contains("Ada Lovelace", "love", ignore_case=True)

# True

any_of = Str.contains("Ada Lovelace", ["Grace", "Ada"])

# True
```

### contains_all

Whether the haystack contains every one of the needles, in any order. `needles`
must be an iterable here rather than a bare string, and `ignore_case` applies
to all of them.

```python title="examples/strings.py"
result = Str.contains_all("Ada Lovelace", ["Ada", "Lovelace"])

# True

partial = Str.contains_all("Ada Lovelace", ["Ada", "Babbage"])

# False
```

### deduplicate

Collapses consecutive runs of `character` down to a single occurrence.
`character` defaults to a space, and is escaped before use, so a regular
expression metacharacter such as `.` is treated literally.

```python title="examples/strings.py"
result = Str.deduplicate("The  Almasix   framework")

# 'The Almasix framework'

path = Str.deduplicate("users//1///posts", "/")

# 'users/1/posts'
```

### doesnt_contain

The negation of `contains`: whether the haystack contains none of the needles.
It takes the same `ignore_case` keyword.

```python title="examples/strings.py"
result = Str.doesnt_contain("Ada Lovelace", "Babbage")

# True

case_matters = Str.doesnt_contain("Ada Lovelace", "ada")

# True
```

### doesnt_end_with

Whether the string ends with none of the needles. `needles` is a single string
or an iterable; the result is `True` only when every one of them fails to
match. Empty needles are ignored, so `Str.doesnt_end_with("Ada", "")` is
`True`.

```python title="examples/strings.py"
result = Str.doesnt_end_with("index.html", ".py")

# True

any_of = Str.doesnt_end_with("index.html", [".html", ".htm"])

# False
```

### doesnt_start_with

Whether the string starts with none of the needles — the negation of
`starts_with`, and useful for checking that a value has not already been
prefixed.

```python title="examples/strings.py"
result = Str.doesnt_start_with("example.com", "https://")

# True
```

### ends_with

Whether the string ends with the needle, or with any needle in an iterable.
Empty needles are skipped rather than matching everything.

```python title="examples/strings.py"
result = Str.ends_with("index.html", ".html")

# True

any_of = Str.ends_with("index.html", [".php", ".html"])

# True
```

### excerpt

Returns a window of `text` around the first case-insensitive occurrence of
`phrase`, with `omission` marking each end that was cut. Options are passed as
a keyword-only mapping: `radius` is how many characters to keep on either side
of the phrase (default `100`) and `omission` is the marker (default `'...'`).
Returns `None` when the phrase is not in the text.

```python title="examples/strings.py"
result = Str.excerpt("This is my beautiful framework", "my", options={"radius": 3})

# '...is my be...'

marked = Str.excerpt("This is my beautiful framework", "my", options={"radius": 3, "omission": "(...)"})

# '(...)is my be(...)'

absent = Str.excerpt("This is my beautiful framework", "absent")

# None
```

With no phrase the text is truncated to `radius` characters instead, with the
omission appended only if anything was removed.

### finish

Ensures the value ends with exactly one `cap`. Any existing run of `cap` at the
end is stripped first, so calling it twice does not double the suffix.

```python title="examples/strings.py"
result = Str.finish("this/string", "/")

# 'this/string/'

trimmed = Str.finish("this/string//", "/")

# 'this/string/'
```

### from_base64

Decodes a base64 string back to text, assuming UTF-8. The counterpart is
`Str.to_base64`.

```python title="examples/strings.py"
result = Str.from_base64("QWxtYXNpeA==")

# 'Almasix'
```

Decoding is not strict: characters outside the base64 alphabet are discarded
rather than reported, so invalid input returns whatever is left (often `''`)
instead of raising. There is no strict mode that raises on invalid input.

### headline

Turns any casing into a space-separated, capitalised phrase, by way of `snake`
— useful for making a label out of a field or class name.

```python title="examples/strings.py"
result = Str.headline("steve_jobs")

# 'Steve Jobs'

from_class = Str.headline("EmailNotificationSent")

# 'Email Notification Sent'
```

Because the value is lower-cased on the way through, runs of capitals are not
preserved: `Str.headline("HTTPRequest")` is `'Httprequest'`.

### initials

Reduces a name to the first letter of each word, upper-cased and followed by a
full stop. `separator` is what goes between the initials, and defaults to a
space.

```python title="examples/strings.py"
result = Str.initials("Ada Lovelace")

# 'A. L.'

tight = Str.initials("Ada Lovelace", "")

# 'A.L.'
```

The value is split on whitespace only, so a hyphenated name counts as one word,
and runs of whitespace do not produce empty initials.

### inline_markdown

Converts a small subset of Markdown to inline HTML, with no wrapping `<p>`.
`&`, `<` and `>` in the input are escaped first, then `**bold**`, `*italic*`,
`` `code` `` and `[text](url)` are converted — nothing else.

```python title="examples/strings.py"
result = Str.inline_markdown("Visit **Almasix** at [the site](https://example.com)")

# 'Visit <strong>Almasix</strong> at <a href="https://example.com">the site</a>'

code = Str.inline_markdown("Use `Str.of()` for *fluent* strings")

# 'Use <code>Str.of()</code> for <em>fluent</em> strings'
```

This is a handful of regular expressions rather than a CommonMark parser, and
the keyword-only `options` mapping is accepted for signature compatibility but
discarded.

### is_

Whether `value` matches the shell-style pattern, where `*` stands for any run
of characters and everything else is literal. An exact string equality also
counts as a match. Pass an iterable of patterns to accept any of them. Note
that the pattern comes first and the value second. The trailing underscore
avoids the Python keyword, and the bare name is kept as an alias reachable
with `getattr(Str, "is")`.

```python title="examples/strings.py"
result = Str.is_("admin/*", "admin/users")

# True

any_of = Str.is_(["admin/*", "api/*"], "api/v1/users")

# True

unmatched = Str.is_("admin/*", "public/index")

# False
```

The pattern must cover the whole value, `?` is not a wildcard, and matching is
always case sensitive — there is no `ignore_case` flag.

### is_ascii

Whether every character in the value can be encoded as ASCII.

```python title="examples/strings.py"
result = Str.is_ascii("Almasix")

# True

accented = Str.is_ascii("Crème")

# False
```

### is_json

Whether the value parses as JSON. Anything `json.loads` accepts counts, so a
bare number or `null` is JSON too, not only objects and arrays.

```python title="examples/strings.py"
result = Str.is_json('{"name": "Ada"}')

# True

invalid = Str.is_json("{name: Ada}")

# False
```

### is_match

Whether the value matches any of the given regular expressions. The patterns
are searched, not anchored, so `r"\d+"` matches anywhere in the value; anchor
with `^` and `$` if you need the whole string to match.

```python title="examples/strings.py"
result = Str.is_match(r"^\d{4}-\d{2}$", "2026-09")

# True

any_of = Str.is_match([r"^v\d+", r"^beta"], "beta-3")

# True
```

Unlike `is_`, which uses `*` globs, this takes real regular expressions. The
related `Str.match` and `Str.match_all` return the matched text instead of a
boolean.

### is_ulid

Whether the value looks like a ULID: 26 characters of Crockford base32 whose
first character is `0`–`7`. The check is a pattern match and is case
insensitive, so a lower-case ULID passes too.

```python title="examples/strings.py"
result = Str.is_ulid("01ARZ3NDEKTSV4RRFFQ69G5FAV")

# True

invalid = Str.is_ulid("not-a-ulid")

# False
```

### is_url

Whether the value parses as a URL, meaning it has both a scheme and a host.
Pass `protocols` to restrict which schemes count. Almasix tests this with
`urllib.parse.urlparse`, so any
scheme is accepted unless you name the ones you want.

```python title="examples/strings.py"
from almasix.support import Str

result = Str.is_url("https://almasix.dev/docs")

# True

result = Str.is_url("http://almasix.dev", ["https"])

# False
```

### is_uuid

Whether the value is a UUID. Almasix hands the string to Python's `uuid.UUID`,
which accepts several shapes — the
32-character unhyphenated form and the `urn:uuid:` form are both true here.

```python title="examples/strings.py"
result = Str.is_uuid("7c9e6679-7425-40de-944b-e07fc1f90ae7")

# True

result = Str.is_uuid("7c9e6679742540de944be07fc1f90ae7")

# True

result = Str.is_uuid("not-a-uuid")

# False
```

### kebab

Converts the string to kebab-case. It is `snake` with a `-` delimiter, so
camel-case boundaries become hyphens and any run of non-alphanumeric characters
collapses into a single hyphen.

```python title="examples/strings.py"
result = Str.kebab("fooBar")

# 'foo-bar'

result = Str.kebab("Foo Bar Baz")

# 'foo-bar-baz'
```

### lcfirst

Lower-cases the first character and leaves the rest of the string alone.

```python title="examples/strings.py"
result = Str.lcfirst("Foo Bar")

# 'foo Bar'
```

### length

The number of characters in the string. An unused `encoding` argument is
accepted for signature compatibility and ignored: Python strings are already
sequences of code points,
so an accented character counts as one either way.

```python title="examples/strings.py"
result = Str.length("Almasix")

# 7

result = Str.length("naïve")

# 5
```

### limit

Truncates the string to at most `limit` characters and appends `end` when it
had to cut. Whitespace left at the cut is stripped first, so a cut landing
after a space does not leave one before the ellipsis. A string that is already
short enough is returned untouched, without `end`. There is no `preserve_words`
argument; the cut is by character count only.

```python title="examples/strings.py"
result = Str.limit("The quick brown fox jumps over the lazy dog", 20)

# 'The quick brown fox...'

result = Str.limit("The quick brown fox", 9, " (…)")

# 'The quick (…)'
```

### lower

Lower-cases the whole string.

```python title="examples/strings.py"
result = Str.lower("Almasix FRAMEWORK")

# 'almasix framework'
```

### ltrim

Strips characters from the start of the string. With no `characters` it strips
whitespace; otherwise `characters` is a set of candidates rather than a prefix,
as with `str.lstrip`.

```python title="examples/strings.py"
result = Str.ltrim("  Almasix  ")

# 'Almasix  '

result = Str.ltrim("xyxAlmasix", "xy")

# 'Almasix'
```

### markdown

Renders Markdown to HTML. No third-party Markdown package is involved or
required: the work is done by Almasix's mail renderer
(`almasix.mail.markdown.render_markdown_component`), which handles `#` and `##`
headings, `**bold**`, links, and paragraphs, and turns a link alone on its line
into a button. Anything it does not know — lists, `*italic*`, code fences — is
left as literal text inside a paragraph, so this is a much smaller Markdown
dialect than full CommonMark. The `options` argument is accepted and
ignored.

```python title="examples/strings.py"
result = Str.markdown("# Release notes")

# '<h1>Release notes</h1>'

result = Str.markdown("A **bold** word.")

# '<p>A <strong>bold</strong> word.</p>'

result = Str.markdown("- one\n- two")

# '<p>- one - two</p>'
```

### mask

Replaces a portion of the string with a repeat of `character`. The arguments
are `(value, character, index, length=None)`: masking starts at `index`, which
may be negative to count from the end, and runs for `length` characters, or to
the end of the string when `length` is omitted.

```python title="resources/views/examples/strings.prism.html"
result = Str.mask("taylor@example.com", "*", 3)

# 'tay***************'

result = Str.mask("taylor@example.com", "*", 3, 6)

# 'tay******ample.com'

result = Str.mask("taylor@example.com", "*", -15, 3)

# 'tay***@example.com'
```

### match

The first match of the regular expression in `subject`. If the pattern has
capture groups, the first group is returned instead of the whole match. When
nothing matches the result is the empty string, not `None`, so use `is_match`
when you want the boolean question answered. Note the argument order: the
pattern comes first, the subject second.

```python title="examples/strings.py"
result = Str.match(r"\d+", "order 42 shipped")

# '42'

result = Str.match(r"foo (bar)", "foo bar")

# 'bar'

result = Str.match(r"\d+", "no digits here")

# ''
```

### match_all

Every match of the regular expression, as a list — or every first capture
group, when the pattern has groups. An empty list when nothing matches.

```python title="resources/views/examples/strings.prism.html"
result = Str.match_all(r"\d+", "a1 b22 c333")

# ['1', '22', '333']

result = Str.match_all(r"\w+@(\w+)\.com", "a@one.com b@two.com")

# ['one', 'two']

result = Str.match_all(r"\d+", "no digits here")

# []
```

### of

Wraps a value in a `Stringable` so the same helpers can be chained fluently.
The value is stringified, `None` becomes the empty string, and the default is
the empty string. `str_()` is the shorter global helper for the same thing.

```python title="examples/strings.py"
result = Str.of("Almasix")

# Stringable('Almasix')

result = Str.of(42)

# Stringable('42')

result = str(Str.of("  Almasix  ").trim().upper())

# 'ALMASIX'
```

### ordered_uuid

A UUID whose leading characters increase with time, so a column of them stays
roughly in insertion order and indexes better than random UUIDs. Almasix
produces this with `uuid.uuid1` — a version 1, time-and-node UUID, not the
timestamp-rearranged UUID some other stacks emit, and it embeds the host's MAC
address.

```python title="examples/strings.py"
# output varies
result = Str.ordered_uuid()

# a 36-character version 1 UUID string, e.g. 'a1adf32e-ab27-11f1-8000-04f0ee26d180'
```

### pad_both

Pads the string on both sides until it is `length` characters long, centring
it. A `pad` longer than one character repeats and is cut short to fit, and the
odd character out goes on the right. A string already at `length` is returned
untouched.

```python title="examples/strings.py"
result = Str.pad_both("Almasix", 12, "_")

# '__Almasix___'

repeated = Str.pad_both("x", 7, "-=")

# '-=-x-=-'
```

### pad_left

Pads the start of the string until it is `length` characters long, repeating
`pad` and cutting it short to fit.

```python title="examples/strings.py"
result = Str.pad_left("7", 3, "0")

# '007'

repeated = Str.pad_left("7", 5, "ab")

# 'abab7'
```

### pad_right

Pads the end of the string until it is `length` characters long, again
repeating `pad` to fit.

```python title="examples/strings.py"
result = Str.pad_right("Almasix", 10, "-")

# 'Almasix---'

repeated = Str.pad_right("7", 5, "ab")

# '7abab'
```

### password

A cryptographically random password of `length` characters, drawn from letters,
digits and the symbols `!@#$%^&*()-_=+[]{};:,.?/`. Turn off any of `letters`,
`numbers`, `symbols` to narrow the alphabet, or turn on `spaces` to add the
space character; if you disable everything, letters are used anyway.

```python title="examples/strings.py"
# output varies
result = Str.password(12)

# a 12-character string mixing letters, digits and symbols, e.g. 'MbbSoCIg#HAg'

result = Str.password(8, symbols=False)

# an 8-character alphanumeric string, e.g. 'ZwsI74hY'
```

### plural

The plural form of an English word. `count` decides whether to pluralise at
all: a count of 1 (or -1) returns the word unchanged, and every other count,
including 0, pluralises. Irregular words come from a small dictionary,
uncountable words such as `sheep` and `information` are never changed, and
everything else goes through a list of suffix rules.

```python title="examples/strings.py"
result = Str.plural("person")

# 'people'

result = Str.plural("category")

# 'categories'

result = Str.plural("car", 1)

# 'car'

result = Str.plural("sheep")

# 'sheep'
```

### plural_studly

Pluralises the last word of a studly-cased string, leaving the earlier words
alone. It takes the same `count` argument as `plural`, so a count of 1 returns
the string unchanged. It rebuilds the string from the words it finds, so any
underscores or other separators in the input are dropped.

```python title="examples/strings.py"
result = Str.plural_studly("UserComment")

# 'UserComments'

result = Str.plural_studly("UserPerson")

# 'UserPeople'

result = Str.plural_studly("VerifiedHuman", 1)

# 'VerifiedHuman'

result = Str.plural_studly("user_comment")

# 'usercomments'
```

### position

The index of the first occurrence of `needle` at or after `offset`, or `False`
when it does not occur. Since a match at the start returns 0, compare with `is
False` rather than testing truthiness.

```python title="examples/strings.py"
result = Str.position("Hello, World!", "World")

# 7

result = Str.position("abcabc", "b", 2)

# 4

result = Str.position("Hello, World!", "x")

# False
```

### random

A cryptographically random alphanumeric string of `length` characters, 16 by
default. Letters and digits only — for symbols use `password`.

```python title="examples/strings.py"
# output varies
result = Str.random(8)

# an 8-character string of letters and digits, e.g. 'puAen0sX'
```

### remove

Removes every occurrence of `search` from `subject`. `search` may be a single
string or an iterable of them, applied in order. Pass `case_sensitive=False` —
keyword-only — to ignore case.

```python title="examples/strings.py"
result = Str.remove("e", "Peter Piper picked a peck")

# 'Ptr Pipr pickd a pck'

result = Str.remove(["a", "e"], "Almasix")

# 'Almsix'

result = Str.remove("A", "Almasix banana", case_sensitive=False)

# 'lmsix bnn'
```

### repeat

Repeats the string `times` times. A count of 0 or less gives the empty string
rather than raising.

```python title="examples/strings.py"
result = Str.repeat("ab", 3)

# 'ababab'

result = Str.repeat("ab", 0)

# ''
```

### replace

Replaces every occurrence of `search` with `replace` in `subject` — note that
the subject is the third argument, not the first. Both `search` and `replace`
may be iterables, in which case they are paired up positionally; a single
`replace` string is used for every search term. `case_sensitive=False` is
keyword-only.

```python title="examples/strings.py"
result = Str.replace("world", "Almasix", "Hello world")

# 'Hello Almasix'

result = Str.replace(["cat", "dog"], "pet", "a cat and a dog")

# 'a pet and a pet'

result = Str.replace("WORLD", "Almasix", "Hello world", case_sensitive=False)

# 'Hello Almasix'
```

### replace_array

Replaces each occurrence of `search` in turn with the next value from
`replace`. Occurrences beyond the end of the replacement sequence keep the
original search string.

```python title="examples/strings.py"
result = Str.replace_array("?", ["8:30", "9:00"], "The event runs from ? to ?")

# 'The event runs from 8:30 to 9:00'

result = Str.replace_array("?", ["8:30"], "from ? to ?")

# 'from 8:30 to ?'
```

### replace_end

Replaces `search` with `replace` only when the subject ends with it, and
returns the subject untouched otherwise.

```python title="examples/strings.py"
result = Str.replace_end("World", "Almasix", "Hello World")

# 'Hello Almasix'

result = Str.replace_end("World", "Almasix", "World Hello")

# 'World Hello'
```

### replace_first

Replaces the first occurrence of `search` in `subject`, leaving any later ones
in place.

```python title="examples/strings.py"
result = Str.replace_first("the", "a", "the quick brown fox jumps over the lazy dog")

# 'a quick brown fox jumps over the lazy dog'
```

### replace_last

Replaces the last occurrence of `search` in `subject`. A subject that does not
contain the search is returned unchanged.

```python title="examples/strings.py"
result = Str.replace_last("the", "a", "the quick brown fox jumps over the lazy dog")

# 'the quick brown fox jumps over a lazy dog'

result = Str.replace_last("x", "y", "abc")

# 'abc'
```

### replace_matches

Replaces everything matching a regular expression. This is `re.sub`, so the
pattern is written in Python syntax with no delimiters and back-references in
the replacement are `\1`, not PHP's `$1`. `replace` may also be a callable,
which receives the `re.Match` and returns the replacement text.

```python title="resources/views/examples/strings.prism.html"
result = Str.replace_matches(r"[^A-Za-z0-9]+", "", "(+1) 501-555-1000")

# '15015551000'

result = Str.replace_matches(r"(\w+)@(\w+)", r"\2 at \1", "ada@example")

# 'example at ada'

result = Str.replace_matches(r"(\d+)", lambda match: "[" + match.group(1) + "]", "order 42")

# 'order [42]'
```

### replace_start

Replaces `search` with `replace` only when the subject starts with it, and
returns the subject untouched otherwise.

```python title="examples/strings.py"
result = Str.replace_start("Hello", "Goodbye", "Hello World")

# 'Goodbye World'

result = Str.replace_start("World", "Almasix", "Hello World")

# 'Hello World'
```

### reverse

Returns the string with its characters in the opposite order.

```python title="examples/strings.py"
from almasix.support import Str

result = Str.reverse("Almasix")

# 'xisamlA'
```

### rtrim

Strips characters from the right-hand end of the string. With no `characters`
it removes whitespace; otherwise `characters` is a *set* of characters to
remove, not a suffix to match, so `".html"` and `"lmth."` behave identically.

```python title="examples/strings.py"
result = Str.rtrim("  Ada  ")

# '  Ada'

result = Str.rtrim("index.html", ".html")

# 'index'
```

### singular

Returns the singular form of an English word, using a table of irregular and
uncountable words plus a list of suffix rules. Words that are already singular,
and uncountable ones such as `equipment` or `series`, come back unchanged. The
capitalisation of the original is preserved for irregular words.

```python title="examples/strings.py"
result = Str.singular("children")

# 'child'

result = Str.singular("Categories")

# 'Category'

result = Str.singular("series")

# 'series'
```

### slug

Builds a URL-friendly slug: transliterates to ASCII, lower-cases, and joins the
remaining words with `separator`. `dictionary` replaces whole substrings before
the non-alphanumeric characters are dropped, and defaults to `{"@": "at"}`. The
`language` argument is accepted for signature compatibility but is ignored —
there is no per-language transliteration table.

```python title="resources/views/examples/strings.prism.html"
result = Str.slug("Crème Brûlée & Café")

# 'creme-brulee-cafe'

result = Str.slug("Crème Brûlée & Café", "_")

# 'creme_brulee_cafe'

result = Str.slug("ada@example.com")

# 'ada-at-examplecom'
```

### snake

Converts the string to snake_case, inserting `delimiter` between a lower-case
or digit character and a following capital, and collapsing any run of
non-alphanumeric characters into a single delimiter. Pass a different
`delimiter` to get other cases — `Str.kebab` is this method with `"-"`.

```python title="examples/strings.py"
result = Str.snake("fooBar")

# 'foo_bar'

result = Str.snake("fooBar", "-")

# 'foo-bar'
```

### squish

Collapses every run of whitespace inside the string into a single space and
trims the ends.

```python title="examples/strings.py"
result = Str.squish("   almasix    is  here ")

# 'almasix is here'
```

### start

Prefixes the string with `prefix` unless it is already there. Repeated copies
of the prefix at the front are collapsed into one, so calling it twice is the
same as calling it once.

```python title="examples/strings.py"
result = Str.start("this/string", "/")

# '/this/string'

result = Str.start("//this/string", "/")

# '/this/string'
```

### starts_with

Whether the string begins with the given needle, or with any needle when passed
an iterable. Empty needles are skipped rather than matching everything, so an
empty string yields `False`.

```python title="examples/strings.py"
result = Str.starts_with("This is my name", "This")

# True

result = Str.starts_with("This is my name", ["That", "This"])

# True

result = Str.starts_with("This is my name", "")

# False
```

### studly

Converts the string to StudlyCase by splitting on every run of non-alphanumeric
characters and upper-casing the first letter of each part. Only the first
letter is touched, so the rest of each part keeps its original case.

```python title="examples/strings.py"
result = Str.studly("foo_bar-baz")

# 'FooBarBaz'
```

### substr

Returns the portion of the string beginning at `start` and running for `length`
characters. With no `length` it runs to the end of the string, and a negative
`start` counts back from the end.

```python title="examples/strings.py"
result = Str.substr("The Almasix Framework", 4, 7)

# 'Almasix'

result = Str.substr("The Almasix Framework", -9)

# 'Framework'
```

### substr_count

Counts the non-overlapping occurrences of `needle`. `offset` skips that many
characters from the front before counting, and `length` limits the count to
that many characters after the offset.

```python title="examples/strings.py"
result = Str.substr_count("If you like ice cream, you will like snow", "like")

# 2

result = Str.substr_count("If you like ice cream, you will like snow", "like", 20)

# 1
```

### substr_replace

Replaces the `length` characters starting at `offset` with `replace`. Note the
argument order: the replacement comes second, before the position. With no
`length` everything from `offset` onwards is replaced; a `length` of `0`
inserts without removing anything.

```python title="examples/strings.py"
result = Str.substr_replace("1300", ":", 2)

# '13:'

result = Str.substr_replace("1300", ":", 2, 0)

# '13:00'
```

### swap

Replaces multiple substrings in one pass, applying the pairs of `map_` in
order. The map is the first argument and the subject the second. The trailing
underscore on `map_` avoids shadowing Python's `map` builtin.

```python title="examples/strings.py"
result = Str.swap({"Tacos": "Burritos", "great": "fantastic"}, "Tacos are great!")

# 'Burritos are fantastic!'
```

### take

Returns the first `limit` characters of the string. A negative `limit` counts
from the end and returns the last characters instead.

```python title="examples/strings.py"
result = Str.take("Build something great!", 5)

# 'Build'

result = Str.take("Build something great!", -6)

# 'great!'
```

### title

Converts the string to Title Case using Python's `str.title`, which upper-cases
the first letter of each run of letters and lower-cases the rest. That means it
capitalises after an apostrophe too — `they're` becomes `They'Re` — so use
`Str.ucwords` or `Str.headline` when the rest of a word must be left alone.

```python title="examples/strings.py"
result = Str.title("a nice title uses the correct case")

# 'A Nice Title Uses The Correct Case'

result = Str.title("they're MINE")

# "They'Re Mine"
```

### to_base64

Encodes the string as standard Base64, after encoding the text itself as UTF-8.
`Str.from_base64` reverses it.

```python title="examples/strings.py"
result = Str.to_base64("Almasix")

# 'QWxtYXNpeA=='

result = Str.to_base64("Crème")

# 'Q3LDqG1l'
```

### transliterate

Reduces the string to ASCII, which is the same function as `Str.ascii`. It
works by NFKD-normalising and dropping anything that will not encode as ASCII,
so accented Latin letters lose their accents but scripts with no ASCII
decomposition — Japanese, Greek, Cyrillic — are removed entirely rather than
replaced with a substitute character.

```python title="examples/strings.py"
result = Str.transliterate("Crème Brûlée")

# 'Creme Brulee'

result = Str.transliterate("日本語 abc")

# ' abc'
```

### trim

Strips characters from both ends of the string. With no `characters` it removes
whitespace; otherwise `characters` is a set of characters to remove from either
end, not a prefix or suffix to match.

```python title="examples/strings.py"
result = Str.trim("  Ada  ")

# 'Ada'

result = Str.trim("-*-Ada-*-", "-*")

# 'Ada'
```

### ucfirst

Upper-cases the first character and leaves the rest of the string exactly as it
was.

```python title="examples/strings.py"
result = Str.ucfirst("almasix framework")

# 'Almasix framework'

result = Str.ucfirst("aLMASIX")

# 'ALMASIX'
```

### ucsplit

Splits the string into a list at each capital letter. A leading run of
lower-case characters becomes its own element, and a string with no capitals
comes back as a single-element list.

```python title="examples/strings.py"
result = Str.ucsplit("FooBarBaz")

# ['Foo', 'Bar', 'Baz']

result = Str.ucsplit("fooBarBaz")

# ['foo', 'Bar', 'Baz']
```

### ucwords

Upper-cases the first letter of every word and leaves every other character
untouched, so `mcDonald` keeps its inner capital where `Str.title` would
flatten it to `Mcdonald`. `delimiters` is the set of characters that start a
new word, and defaults to the whitespace characters.

```python title="examples/strings.py"
result = Str.ucwords("ronald mcDonald")

# 'Ronald McDonald'

result = Str.ucwords("hello|world", "|")

# 'Hello|World'
```

### ulid

Returns a new 26-character ULID in Crockford Base32: ten characters of
millisecond timestamp followed by sixteen random characters. Because the prefix
is time-based, ULIDs generated in order sort in order. `Str.is_ulid` tests the
format.

```python title="examples/strings.py"
# output varies
result = Str.ulid()

# a 26-character uppercase Crockford Base32 string, e.g. '01M1ZJ77QPGDDKA9YV761PJFY5'
```

### unwrap

Removes `before` from the start and `after` from the end of the string. `after`
defaults to `before`. The string is returned unchanged unless *both* ends
match, so it will not strip a half-open pair.

```python title="examples/strings.py"
result = Str.unwrap('"Almasix"', '"')

# 'Almasix'

result = Str.unwrap("{Almasix}", "{", "}")

# 'Almasix'

result = Str.unwrap('"Almasix', '"')

# '"Almasix'
```

### upper

Returns the string in upper case.

```python title="examples/strings.py"
result = Str.upper("almasix")

# 'ALMASIX'
```

### uuid

Returns a new random (version 4) UUID as a string. `Str.ordered_uuid` returns a
version 1 UUID instead, and `Str.is_uuid` tests the format.

```python title="examples/strings.py"
# output varies
result = Str.uuid()

# a 36-character version 4 UUID, e.g. '5a9317a0-b431-44a4-944c-238b2e25cad2'
```

### word_count

Counts the words in the string, where a word is any run of characters separated
by whitespace. Punctuation attached to a word does not start a new one.

```python title="examples/strings.py"
result = Str.word_count("Hello, World!")

# 2
```

### word_wrap

Inserts `break_str` after every `characters` characters. It counts characters
rather than looking for word boundaries, so a break can land inside a word, and
the `cut` argument is accepted but has no effect.

```python title="examples/strings.py"
result = Str.word_wrap("The quick brown fox", 10, "<br>")

# 'The quick <br>brown fox'

result = Str.word_wrap("The quick brown fox jumped", 10)

# 'The quick \nbrown fox \njumped'
```

### words

Truncates the string to the first `words` whitespace-separated words and
appends `end`. Runs of whitespace between the kept words are collapsed to
single spaces. A string with no more than `words` words is returned untouched,
without `end`.

```python title="examples/strings.py"
result = Str.words("Perfectly balanced, as all things should be.", 3)

# 'Perfectly balanced, as...'

result = Str.words("Perfectly balanced, as all things should be.", 3, " >>>")

# 'Perfectly balanced, as >>>'
```

### wrap

Surrounds the string with `before` and `after`. `after` defaults to `before`,
so a single argument wraps both ends with the same text. `Str.unwrap` reverses
it.

```python title="examples/strings.py"
result = Str.wrap("Almasix", '"')

# '"Almasix"'

result = Str.wrap("is", "This ", " Almasix!")

# 'This is Almasix!'
```

## Fluent strings

The same surface, bound to a subject by `str_()`. Every method returns a new
`Stringable` unless the section says otherwise, so chains never alter what they
started from.

### after

Everything after the first occurrence of `search`, as a new `Stringable`.

```python title="resources/views/examples/strings.prism.html"
from almasix.support import str_

result = str_("ada@example.com").after("@").value()

# 'example.com'
```

### after_last

Everything after the last occurrence of `search`.

```python title="app/http/controllers/example_controller.py"
result = str_("app/Http/Controllers/UserController.py").after_last("/").value()

# 'UserController.py'
```

### apa

The value in approximate APA title case, with the short words left lower-case
unless they open or close the title.

```python title="examples/strings.py"
result = str_("a nice title for the report").apa().value()

# 'A Nice Title for the Report'
```

### append

Concatenates every argument to the end of the value; there is no `Str.append`,
this exists only on `Stringable`. `Stringable` is immutable, so the call
returns a new instance and leaves the subject alone.

```python title="examples/strings.py"
name = str_("Ada")

result = name.append(" Lovelace").value()

# 'Ada Lovelace'

unchanged = name.value()

# 'Ada'
```

### ascii

Drops accents and every other non-ASCII character.

```python title="examples/strings.py"
result = str_("Crème brûlée").ascii().value()

# 'Creme brulee'
```

### basename

The last component of the value read as a filesystem path, with `suffix`
removed when the name ends with it. It goes through `pathlib`, so a trailing
separator is ignored. `Stringable` only — there is no `Str.basename`.

```python title="examples/strings.py"
result = str_("/var/www/app/User.py").basename(".py").value()

# 'User'
```

### before

Everything before the first occurrence of `search`.

```python title="resources/views/examples/strings.prism.html"
result = str_("ada@example.com").before("@").value()

# 'ada'
```

### before_last

Everything before the last occurrence of `search`.

```python title="app/http/controllers/example_controller.py"
result = str_("app/Http/Controllers/UserController.py").before_last("/").value()

# 'app/Http/Controllers'
```

### between

The portion between the first `from_` and the first `to` that follows it. The
first closing delimiter ends the match, so nested delimiters are not balanced.

```python title="examples/strings.py"
result = str_("The [quick] brown [fox]").between("[", "]").value()

# 'quick'

nested = str_("[a[b]]").between("[", "]").value()

# 'a[b'
```

### between_first

Identical to `between` — Almasix implements it by calling `between`, so both
stop at the first `to`.

```python title="examples/strings.py"
result = str_("[a[b]]").between_first("[", "]").value()

# 'a[b'
```

### camel

The value in camelCase.

```python title="examples/strings.py"
result = str_("user_full_name").camel().value()

# 'userFullName'
```

### char_at

The character at `index`. Unlike `Str.char_at`, which hands back a plain
string, the fluent form wraps the hit in a `Stringable`; an index outside the
string still returns the bool `False`, so the chain ends there.

```python title="examples/strings.py"
result = str(str_("Almasix").char_at(0))

# 'A'

missing = str_("Almasix").char_at(10)

# False
```

### chop_end

The value with the first matching suffix removed, if any of `needle` matches.

```python title="examples/strings.py"
result = str_("report.csv").chop_end(".csv").value()

# 'report'
```

### chop_start

The value with the first matching prefix removed.

```python title="examples/strings.py"
result = str_("https://almasix.dev").chop_start("https://").value()

# 'almasix.dev'
```

### class_basename

The part of the value after the last `.` or `\`, so both Python dotted paths
and PHP-style class names reduce to the class name. `Stringable` only.

```python title="app/models/example.py"
result = str_("app.models.user.User").class_basename().value()

# 'User'

php = str_("App\\Models\\User").class_basename().value()

# 'User'
```

### contains

Whether any of `needles` occurs in the value. Returns a `bool`, so it
terminates the chain.

```python title="examples/strings.py"
result = str_("Ada Lovelace").contains("love", ignore_case=True)

# True
```

### contains_all

Whether every one of `needles` occurs in the value. Returns a `bool`.

```python title="examples/strings.py"
result = str_("Ada Lovelace").contains_all(["Ada", "Lovelace"])

# True
```

### dd

Prints the current value to stderr in a bordered panel and then halts by
raising `almasix.debug.DumpAndDie`, which the framework turns into a stopped
request. It returns `None` and has no `Str` twin. In application code you call
it bare — `str_(value).dd()` — and nothing after it runs; the example catches
the exception only so that it can be executed here.

```python title="examples/strings.py"
from almasix.debug import DumpAndDie

halted = False

try:
    str_("Ada Lovelace").dd()
except DumpAndDie:
    halted = True

# True
```

### decrypt

Decrypts a string produced by `encrypt`, using the application key, and returns
the plain text as a new `Stringable`. Raises if the payload was not encrypted
with the current key. `Stringable` only.

```python title="examples/strings.py"
# needs a booted application
token = str_("secret").encrypt()

result = token.decrypt().value()

# 'secret'
```

### deduplicate

Collapses runs of `character` — a space unless you say otherwise — down to one.

```python title="examples/strings.py"
result = str_("The   Almasix    framework").deduplicate().value()

# 'The Almasix framework'

path = str_("stop//go///now").deduplicate("/").value()

# 'stop/go/now'
```

### dirname

The parent of the value read as a filesystem path, climbing `levels` times.
`Stringable` only.

```python title="examples/strings.py"
result = str_("/var/www/app/User.py").dirname().value()

# '/var/www/app'

up = str_("/var/www/app/User.py").dirname(2).value()

# '/var/www'
```

### doesnt_contain

The negation of `contains`: `True` when none of `needles` occurs. Returns a
`bool`.

```python title="examples/strings.py"
result = str_("Ada Lovelace").doesnt_contain("Babbage")

# True
```

### doesnt_end_with

Whether the value ends with none of `needles`. Returns a `bool`.

```python title="examples/strings.py"
result = str_("report.csv").doesnt_end_with(".json")

# True
```

### doesnt_start_with

Whether the value starts with none of `needles`. Returns a `bool`.

```python title="examples/strings.py"
result = str_("report.csv").doesnt_start_with(["draft", "tmp"])

# True
```

### dump

Prints the current value to stderr in a bordered panel and returns the same
instance, so you can drop it into the middle of a chain to see what a step
produced. It has no `Str` twin, and unlike `dd` it does not halt.

```python title="examples/strings.py"
result = str_("Ada").dump().upper().value()

# 'ADA'
```

### encrypt

Encrypts the value with the application key and returns the ciphertext as a new
`Stringable`; `decrypt` reverses it. `Stringable` only.

```python title="examples/strings.py"
# needs a booted application
result = str_("secret").encrypt().decrypt().value()

# 'secret'
```

### ends_with

Whether the value ends with any of `needles`. Returns a `bool`.

```python title="examples/strings.py"
result = str_("report.csv").ends_with([".csv", ".tsv"])

# True
```

### exactly

Whether the value equals `str(value)` — the argument is stringified first, so a
number compares equal to its digits. Returns a `bool`.

```python title="examples/strings.py"
result = str_("Ada").exactly("Ada")

# True

coerced = str_("42").exactly(42)

# True
```

### excerpt

The window of text around the first case-insensitive match for `phrase`, padded
by `radius` characters on each side and marked with `omission`; both come from
the `options` dict. Returns a `Stringable`, or `None` when the phrase is
absent, so guard the chain.

```python title="examples/strings.py"
result = str_("A long sentence about the Almasix framework and its helpers").excerpt("Almasix", options={"radius": 10}).value()

# '...about the Almasix framework...'

missing = str_("A long sentence about Almasix").excerpt("Django")

# None
```

### explode

Splits the value on a literal `delimiter` and returns a plain `list[str]`, not
a `Stringable`. `Stringable` only; for a regular expression, use `split`.

```python title="examples/strings.py"
result = str_("a,b,c").explode(",")

# ['a', 'b', 'c']
```

### finish

The value with a single trailing `cap`, adding it if it is missing and
collapsing it if it is repeated.

```python title="examples/strings.py"
result = str_("path/to").finish("/").value()

# 'path/to/'
```

### from_base

Base64-decodes the value and returns the decoded text as a new `Stringable`. It
exists only on `Stringable` and is a thin alias for `Str.from_base64`; the
encoding direction is `to_base`.

```python title="examples/strings.py"
result = str_("QWxtYXNpeA==").from_base().value()

# 'Almasix'
```

### from_base64

The fluent form of `Str.from_base64`, with the same result as `from_base`.

```python title="examples/strings.py"
result = str_("QWxtYXNpeA==").from_base64().value()

# 'Almasix'
```

### hash

Hashes the value with the application's hasher — bcrypt by default — and
returns the digest as a new `Stringable`. Pass `driver` to pick a configured
hasher such as `argon2`. Each call salts afresh, so the digest differs every
time. `Stringable` only.

```python title="examples/strings.py"
# needs a booted application
result = str_("secret").hash().value()

# '$2b$12$LwZlKr53eiax0x8gsw3lI.Z4JsKVy7TOOTHsrd3.RzSVYhvwdTEoe'
```

### headline

The value split into words and capitalised, whatever casing or separators it
arrived in.

```python title="examples/strings.py"
result = str_("steve_jobs_and_bill").headline().value()

# 'Steve Jobs And Bill'
```

### initials

The first letter of each word, each followed by a full stop and joined by
`separator`.

```python title="examples/strings.py"
result = str_("Ada Lovelace").initials().value()

# 'A. L.'

tight = str_("Ada Lovelace").initials("").value()

# 'A.L.'
```

### inline_markdown

Renders the inline Markdown — emphasis, code spans and links — as HTML,
escaping the rest.

```python title="examples/strings.py"
result = str_("**Almasix** is [fast](https://almasix.dev)").inline_markdown().value()

# '<strong>Almasix</strong> is <a href="https://almasix.dev">fast</a>'
```

### is_

Whether the value matches any of the given patterns, where `*` stands for any
run of characters. Returns a `bool`. The trailing underscore avoids the
Python keyword.

```python title="examples/strings.py"
result = str_("foo/bar/baz").is_("foo/*")

# True
```

### is_ascii

Whether the value is entirely ASCII. Returns a `bool`.

```python title="examples/strings.py"
result = str_("Almasix").is_ascii()

# True

accented = str_("Crème").is_ascii()

# False
```

### is_empty

Whether the value is the empty string. Returns a `bool`. `Stringable` only —
note that `str_(None)` holds `""`, so it reports empty rather than failing.

```python title="examples/strings.py"
result = str_("  ").trim().is_empty()

# True

nothing = str_(None).is_empty()

# True
```

### is_json

Whether the value parses as JSON. Returns a `bool`.

```python title="examples/strings.py"
result = str_('{"name": "Ada"}').is_json()

# True
```

### is_match

Whether the value matches any of the given regular expressions, searched
anywhere in the string rather than anchored. Returns a `bool`. `test` is the
same check under the `test` alias.

```python title="examples/strings.py"
result = str_("Almasix 1.4").is_match(r"\d+\.\d+")

# True

several = str_("Report 2026").is_match([r"^\d+$", r"\s\d{4}$"])

# True
```

### is_not_empty

The negation of `is_empty`. Returns a `bool`.

```python title="examples/strings.py"
result = str_("Ada").is_not_empty()

# True
```

### is_ulid

Whether the value is a 26-character Crockford Base32 ULID. Returns a `bool`.

```python title="examples/strings.py"
result = str_("01ARZ3NDEKTSV4RRFFQ69G5FAV").is_ulid()

# True
```

### is_url

Whether the value parses as a URL with both a scheme and a host. Pass
`protocols` to restrict the accepted schemes. Returns a `bool`.

```python title="examples/strings.py"
result = str_("https://almasix.dev/docs").is_url()

# True

wrong_scheme = str_("http://almasix.dev").is_url(["https"])

# False
```

### is_uuid

Whether the current value parses as a UUID; returns a `bool`, so the chain ends
here.

```python title="examples/helpers.py"
from almasix.support import str_

result = str_("  550e8400-e29b-41d4-a716-446655440000  ").trim().is_uuid()

# True
```

### kebab

Converts the value to kebab-case.

```python title="examples/strings.py"
result = str_("fooBar baz").kebab().value()

# foo-bar-baz
```

### lcfirst

Lower-cases the first character and leaves the rest alone.

```python title="examples/strings.py"
result = str_("foo bar").studly().lcfirst().value()

# fooBar
```

### length

The number of characters in the value, as an `int`; the chain ends here.

```python title="examples/strings.py"
result = str_("  almasix  ").trim().length()

# 7
```

### limit

Truncates to `limit` characters, appending `end` (`"..."` by default) when the
value was actually cut.

```python title="examples/strings.py"
result = str_("The quick brown fox").limit(9).value()

# The quick...

result = str_("The quick brown fox").limit(9, " (...)").value()

# The quick (...)
```

### lower

Lower-cases the whole value.

```python title="examples/strings.py"
result = str_("ALMASIX Framework").lower().value()

# almasix framework
```

### ltrim

Strips characters from the start of the value; whitespace when no argument is
given.

```python title="examples/strings.py"
result = str_("000042").ltrim("0").value()

# 42
```

### markdown

Renders the value as Markdown and wraps the resulting HTML in a new
`Stringable`.

```python title="examples/strings.py"
result = str_("# Title").markdown().value()

# <h1>Title</h1>
```

### mask

Replaces a portion of the value with the given character, starting at `index`
and running to the end unless a `length` is given.

```python title="examples/strings.py"
result = str_("4111111111111111").mask("*", 4).value()

# 4111************

result = str_("4111111111111111").mask("*", 4, 8).value()

# 4111********1111
```

### match

The first match for the pattern, or its first capture group when the pattern
has one, as a `Stringable` you can keep chaining from. An unmatched pattern
gives an empty string.

```python title="examples/strings.py"
result = str_("foo bar").match(r"f(o+)").upper().value()

# OO
```

### match_all

Every match for the pattern — or every first capture group — as a plain
`list[str]`, so the chain ends here.

```python title="examples/strings.py"
result = str_("foo bar foo").match_all(r"foo")

# ['foo', 'foo']
```

### new_line

Appends `count` newline characters (one by default) and returns a new
`Stringable`; the receiver is unchanged. There is no `Str` twin for this — it
exists only on the fluent wrapper, for building up multi-line text between
`append` calls.

```python title="examples/strings.py"
result = str_("Dear Ada").new_line(2).append("Regards").value()

# 'Dear Ada\n\nRegards'
```

### of

Returns a new `Stringable` around the same value. The fluent form takes no
useful argument: the delegate binds the current value to `Str.of`'s only
parameter, so anything you pass is discarded.

```python title="examples/strings.py"
result = str_("almasix").upper().of().value()

# ALMASIX
```

### ordered_uuid

A time-ordered (version 1) UUID. Like the other generators on this wrapper it
ignores the current value, so it is only worth calling on an empty
`Stringable`.

```python title="examples/strings.py"
# output varies
result = str_("").ordered_uuid().value()

# 12b5cdbc-ab28-11f1-8000-04f0ee26d180
```

### pad_both

Pads both sides of the value up to `length`, repeating `pad` to fit.

```python title="examples/strings.py"
result = str_("almasix").pad_both(12, "_").value()

# __almasix___
```

### pad_left

Pads the start of the value up to `length`.

```python title="examples/strings.py"
result = str_(7).pad_left(3, "0").value()

# 007
```

### pad_right

Pads the end of the value up to `length`.

```python title="examples/strings.py"
result = str_("7").pad_right(3, ".").value()

# 7..
```

### password

Generates a random password of `length` characters. It discards the current
value rather than deriving anything from it.

```python title="examples/strings.py"
# output varies
result = str_("").password(12).value()

# !RaWvmK!8fuK
```

### pipe

Passes the whole `Stringable` — not the underlying `str` — to the callback and
returns whatever the callback returns. Return another `Stringable` to stay in
the chain; return anything else and the chain ends with that value's type.
Because the argument is a `Stringable`, built-ins such as `len` fail on it;
reach for `.value()` inside the callback. This method has no `Str` twin.

```python title="examples/strings.py"
result = str_("Ada Lovelace").pipe(lambda s: len(s.value()))

# 12

result = str_("Ada Lovelace").pipe(lambda s: s.lower().slug()).value()

# ada-lovelace
```

### plural

Pluralises the value. Pass a count to keep the singular form when it is 1.

```python title="examples/strings.py"
result = str_("child").plural().value()

# children

result = str_("child").plural(1).value()

# child
```

### plural_studly

Pluralises only the last word of a StudlyCase value, leaving the casing intact.

```python title="examples/strings.py"
result = str_("UserProfile").plural_studly().value()

# UserProfiles
```

### position

The index of the first occurrence of the needle as an `int`, or `False` when it
is absent — either way the chain ends here.

```python title="examples/strings.py"
result = str_("almasix framework").position("framework")

# 8

result = str_("almasix framework").position("zzz")

# False
```

### prepend

Puts the given values in front of the current one. It returns a new
`Stringable`; the receiver keeps its old value.

```python title="examples/strings.py"
result = str_("world").prepend("hello, ").ucfirst().value()

# Hello, world
```

### random

Generates a random alphanumeric string of the given length. It ignores the
current value.

```python title="examples/strings.py"
# output varies
result = str_("").random(8).value()

# GO2sl6Sh
```

### remove

Deletes every occurrence of `search` (a string or an iterable of them). Pass
`case_sensitive=False` to ignore case.

```python title="examples/strings.py"
result = str_("Peter Piper").remove("e").value()

# Ptr Pipr

result = str_("Peter Piper").remove("p", case_sensitive=False).value()

# eter ier
```

### repeat

Repeats the value the given number of times.

```python title="examples/strings.py"
result = str_("-").repeat(5).value()

# -----
```

### replace

Replaces occurrences of `search` with `replace`; both may be lists, which are
paired up positionally. `case_sensitive=False` matches without regard to case.

```python title="examples/strings.py"
result = str_("Almasix rocks").replace("rocks", "ships").value()

# Almasix ships

result = str_("a b c").replace(["a", "b"], ["x", "y"]).value()

# x y c
```

### replace_array

Replaces successive occurrences of `search` with successive entries of
`replace`.

```python title="examples/strings.py"
result = str_("Between ? and ?").replace_array("?", ["8:30", "9:00"]).value()

# Between 8:30 and 9:00
```

### replace_end

Replaces `search` only when the value ends with it.

```python title="examples/strings.py"
result = str_("almasix.py.py").replace_end(".py", ".txt").value()

# almasix.py.txt
```

### replace_first

Replaces the first occurrence of `search`.

```python title="examples/strings.py"
result = str_("a-a-a").replace_first("a", "b").value()

# b-a-a
```

### replace_last

Replaces the last occurrence of `search`.

```python title="examples/strings.py"
result = str_("a-a-a").replace_last("a", "b").value()

# a-a-b
```

### replace_matches

Replaces everything matching the regular expression; `replace` may be a
replacement string or a callback receiving the match object.

```python title="examples/strings.py"
result = str_("almasix 123 framework 456").replace_matches(r"[0-9]+", "#").value()

# almasix # framework #

result = str_("almasix 12").replace_matches(r"[0-9]+", lambda m: "<" + m.group(0) + ">").value()

# almasix <12>
```

### replace_start

Replaces `search` only when the value starts with it.

```python title="examples/strings.py"
result = str_("http://example.com").replace_start("http://", "https://").value()

# https://example.com
```

### reverse

Reverses the value.

```python title="examples/strings.py"
result = str_("almasix").reverse().upper().value()

# XISAMLA
```

### rtrim

Strips characters from the end of the value; whitespace when no argument is
given.

```python title="examples/strings.py"
result = str_("almasix...").rtrim(".").value()

# almasix
```

### singular

Singularises the value.

```python title="examples/strings.py"
result = str_("children").singular().value()

# child
```

### slug

Turns the value into a URL-friendly slug, with `-` as the separator unless you
pass another.

```python title="examples/strings.py"
result = str_("Almasix Framework!").slug().value()

# almasix-framework

result = str_("Almasix Framework").slug("_").value()

# almasix_framework
```

### snake

Converts the value to snake_case.

```python title="examples/strings.py"
result = str_("fooBar baz").snake().value()

# foo_bar_baz
```

### split

Splits the value on a regular expression and returns a plain `list[str]`, so
the chain ends here. `limit` is the maximum number of splits to perform, not
the number of pieces to produce; `0`, the default, means no limit. This method
exists only on `Stringable` — `Str` has no `split`.

```python title="examples/strings.py"
result = str_("a1b22c3d").split(r"[0-9]+")

# ['a', 'b', 'c', 'd']

result = str_("a1b22c3d").split(r"[0-9]+", 1)

# ['a', 'b22c3d']
```

### squish

Collapses runs of whitespace into single spaces and trims the ends.

```python title="examples/strings.py"
result = str_("   Almasix    Framework   ").squish().value()

# Almasix Framework
```

### start

Prefixes the value with the given string, collapsing any prefixes already there
so it appears exactly once.

```python title="examples/strings.py"
result = str_("///almasix").start("/").value()

# /almasix
```

### starts_with

Whether the value begins with the needle, or with any needle when given an
iterable; returns a `bool`.

```python title="examples/strings.py"
result = str_("Almasix Framework").lower().starts_with(["alm", "zzz"])

# True
```

### strip_tags

Removes HTML and XML tags, keeping the text between them. Pass a
comma-separated list of tag names to `allowed` to keep those tags intact. There
is no `Str` twin — this lives only on the fluent wrapper.

```python title="examples/strings.py"
result = str_("<p>Hello <b>you</b></p>").strip_tags().value()

# Hello you

result = str_("<p>Hello <b>you</b></p>").strip_tags("b").value()

# Hello <b>you</b>
```

### studly

Converts the value to StudlyCase.

```python title="examples/strings.py"
result = str_("foo_bar baz").studly().value()

# FooBarBaz
```

### substr

The portion of the value beginning at `start`, running to the end unless a
`length` is given. A negative `start` counts back from the end.

```python title="examples/strings.py"
result = str_("Almasix Framework").substr(8).value()

# Framework

result = str_("Almasix Framework").substr(0, 7).lower().value()

# almasix
```

### substr_count

Counts the non-overlapping occurrences of the needle in the wrapped string and
returns an `int`, which ends the chain; `offset` skips that many leading
characters before counting.

```python title="examples/helpers.py"
from almasix.support import str_

result = str_("If you like ice cream, you will like snow").substr_count("like")

# 2

result = str_("If you like ice cream, you will like snow").substr_count("like", 20)

# 1
```

### substr_replace

Replaces the characters starting at `offset` with the given text; the
replacement comes first and a `length` of `0` inserts without removing
anything.

```python title="examples/strings.py"
result = str_("Hello, World").substr_replace("Python", 7, 5).value()

# 'Hello, Python'

result = str_("1300").substr_replace(":", 2, 0).value()

# '13:00'
```

### swap

Replaces several substrings in one pass, applying the pairs of `map_` in order;
the trailing underscore avoids shadowing Python's `map` builtin.

```python title="examples/strings.py"
result = str_("Tacos are great!").swap({"Tacos": "Burritos", "great": "fantastic"}).value()

# 'Burritos are fantastic!'
```

### take

Returns the first `limit` characters, or the last ones when `limit` is
negative.

```python title="examples/strings.py"
result = str_("Build something").take(5).value()

# 'Build'

result = str_("Build something").take(-9).value()

# 'something'
```

### tap

Passes the `Stringable` to the callback and then returns that same `Stringable`
regardless of what the callback returns, so the chain continues from the value
it had before the call. Use it to observe or record an intermediate value —
logging it, appending it to a list — without breaking the chain apart into
separate statements. There is no `Str` twin; this method exists only on the
fluent surface.

```python title="examples/strings.py"
seen = []
result = str_("ada").tap(lambda s: seen.append(s.value())).upper().value()

# 'ADA'
# ['ada']
```

### test

Whether the wrapped string matches the given regular expression, returning a
`bool` that ends the chain. The pattern is searched for anywhere in the string
rather than anchored to it, so `[0-9]{4}` matches a string that merely contains
four digits; anchor it yourself with `^` and `$` when you need a full match.
There is no `Str.test` — the static equivalent is `Str.is_match`.

```python title="examples/strings.py"
result = str_("almasix-2026").test(r"[0-9]{4}")

# True

result = str_("order-4417").test(r"^[a-z]+$")

# False
```

### title

Title-cases the string with Python's `str.title`, which also lower-cases the
rest of each word.

```python title="examples/strings.py"
result = str_("a nice title").title().value()

# 'A Nice Title'
```

### to_base

Base64-encodes the wrapped string and returns a new `Stringable`, with
`from_base` as its inverse. Both are fluent-only spellings — there is no
`Str.to_base` or `Str.from_base` — and they call the same code as `to_base64`
and `from_base64`, so the two pairs of names are interchangeable.

```python title="examples/strings.py"
result = str_("almasix").to_base().value()

# 'YWxtYXNpeA=='

result = str_("almasix").to_base().from_base().value()

# 'almasix'
```

### to_base64

Encodes the string as standard Base64 after encoding the text as UTF-8;
identical to `to_base`.

```python title="examples/strings.py"
result = str_("almasix").to_base64().value()

# 'YWxtYXNpeA=='
```

### to_boolean

Returns a `bool`, ending the chain: `True` when the string is one of `1`,
`true`, `yes` or `on` compared case-insensitively, and `False` for anything
else, including an empty string.

```python title="examples/strings.py"
result = str_("yes").to_boolean()

# True

result = str_("off").to_boolean()

# False
```

### to_float

Parses the string with `float` and returns a `float`, ending the chain. A
string that is not a number raises `ValueError`.

```python title="examples/strings.py"
result = str_("1.75").to_float()

# 1.75
```

### to_integer

Parses the string with `int` and returns an `int`, ending the chain.
Surrounding whitespace is tolerated by `int` itself, but anything else — a
decimal point included — raises `ValueError`.

```python title="examples/strings.py"
result = str_(" 42 ").trim().to_integer()

# 42
```

### to_string

Unwraps the chain and returns the underlying `str`. It is the same as `value`,
and the same as calling `str()` on the `Stringable`; all three exist so the
chain can be terminated in whichever style reads best. There is no `Str` twin.

```python title="examples/strings.py"
result = str_("Ada").upper().to_string()

# 'ADA'
```

### transliterate

Reduces the string to ASCII by NFKD-normalising and dropping whatever will not
encode, which is the same function as `ascii`.

```python title="examples/strings.py"
result = str_("Düsseldorf").transliterate().value()

# 'Dusseldorf'
```

### trim

Strips characters from both ends of the string. With no argument it removes
whitespace; otherwise the argument is a *set* of characters to strip from
either end, not a prefix or suffix to match, so `"_"` and `"__"` behave
identically. `ltrim` and `rtrim` are the one-sided forms.

```python title="examples/strings.py"
result = str_("  padded  ").trim().value()

# 'padded'

result = str_("__name__").trim("_").value()

# 'name'
```

### ucfirst

Upper-cases the first character and leaves the rest of the string as it was.

```python title="examples/strings.py"
result = str_("ada lovelace").ucfirst().value()

# 'Ada lovelace'
```

### ucsplit

Splits the string at each capital letter and returns a plain `list[str]`, which
ends the chain.

```python title="examples/strings.py"
result = str_("FooBarBaz").ucsplit()

# ['Foo', 'Bar', 'Baz']
```

### ucwords

Upper-cases the first letter of every word and leaves every other character
untouched, so an inner capital survives where `title` would flatten it.

```python title="examples/strings.py"
result = str_("ronald mcDonald").ucwords().value()

# 'Ronald McDonald'
```

### ulid

Returns a new 26-character ULID, discarding the wrapped string entirely —
`Str.ulid` takes no subject, so the fluent form is a constructor rather than a
transformation.

```python title="examples/strings.py"
# output varies
result = str_("ignored").ulid().value()

# a fresh 26-character Crockford Base32 ULID, e.g. '01M1ZJD7DMYHD202AAW3XYK515'
```

### unless

The inverse of `when`: runs `callback` when the condition is falsy, and the
optional `default` when it is truthy. Both receive the `Stringable` and the
chain continues from whatever they return, so it is a way to apply a
transformation only in the absence of some condition. There is no `Str` twin.

```python title="examples/strings.py"
result = str_("ada").unless(False, lambda s: s.upper()).value()

# 'ADA'

result = str_("ada").unless(True, lambda s: s.upper(), lambda s: s.title()).value()

# 'Ada'
```

### unwrap

Removes `before` from the start and `after` from the end, with `after`
defaulting to `before`; both ends must match or the string comes back
unchanged.

```python title="examples/strings.py"
result = str_('"quoted"').unwrap('"').value()

# 'quoted'

result = str_('"half').unwrap('"').value()

# '"half'
```

### upper

Returns the string in upper case.

```python title="examples/strings.py"
result = str_("shout").upper().value()

# 'SHOUT'
```

### uuid

Returns a new random version 4 UUID, discarding the wrapped string — like
`ulid`, the fluent form is a constructor because `Str.uuid` takes no subject.

```python title="examples/strings.py"
# output varies
result = str_("ignored").uuid().value()

# a fresh version 4 UUID, e.g. '957e3f4e-e940-41cd-bde3-a6c628feb418'
```

### value

Unwraps the chain and returns the underlying `str`. This is the usual way to
finish a fluent expression, and is identical to `to_string` and to `str()` on
the `Stringable`. It is fluent-only: a `Str` call already returns a plain
string.

```python title="examples/strings.py"
result = str_("  hi  ").trim().value()

# 'hi'
```

### when

Runs `callback` when the condition is truthy, or the optional `default` when it
is not, and continues the chain from whatever was returned. The callback
receives the `Stringable` as its only argument; a callback that returns `None`
is treated as having done nothing and the original value carries on. With
neither a callback nor a default the call is a no-op. The condition is
evaluated for plain truthiness, so passing a function as the condition always
counts as true. There is no `Str` twin.

```python title="examples/strings.py"
result = str_("ada").when(True, lambda s: s.upper()).value()

# 'ADA'

result = str_("ada").when(False, lambda s: s.upper(), lambda s: s.title()).value()

# 'Ada'

result = str_("ada").when(True, lambda s: None).value()

# 'ada'
```

### when_contains

Runs the callback when the string contains the needle. This is the first of the
`when_*` family, all of which are generated from a table of tests and share one
shape: the arguments for the test come first, the callback is the last
positional argument, and an optional `default` follows it for the case where
the test fails. The callback receives the `Stringable` and the chain continues
from what it returns, exactly as with `when` — these are shorthands for `when`
with the matching predicate. None of them has a `Str` twin.

```python title="examples/strings.py"
result = str_("tony stark").when_contains("tony", lambda s: s.title()).value()

# 'Tony Stark'

result = str_("bruce wayne").when_contains("tony", lambda s: s.title(), lambda s: s.upper()).value()

# 'BRUCE WAYNE'
```

### when_contains_all

Runs the callback when the string contains every one of the given needles.

```python title="examples/strings.py"
result = str_("tony stark").when_contains_all(["tony", "stark"], lambda s: s.title()).value()

# 'Tony Stark'
```

### when_doesnt_end_with

Runs the callback when the string ends with none of the given needles.

```python title="examples/strings.py"
result = str_("framework").when_doesnt_end_with(".py", lambda s: s.append(".py")).value()

# 'framework.py'
```

### when_doesnt_start_with

Runs the callback when the string starts with none of the given needles.

```python title="examples/strings.py"
result = str_("almasix").when_doesnt_start_with("the ", lambda s: s.prepend("the ")).value()

# 'the almasix'
```

### when_empty

Runs the callback when the string is empty. The test takes no arguments, so the
callback is the first argument.

```python title="examples/strings.py"
result = str_("").when_empty(lambda s: s.append("anonymous")).value()

# 'anonymous'
```

### when_ends_with

Runs the callback when the string ends with the needle, or with any of them
when given an iterable.

```python title="examples/strings.py"
result = str_("main.py").when_ends_with(".py", lambda s: s.basename(".py")).value()

# 'main'
```

### when_exactly

Runs the callback when the string equals the given value, compared as strings.

```python title="examples/strings.py"
result = str_("almasix").when_exactly("almasix", lambda s: s.upper()).value()

# 'ALMASIX'
```

### when_is

Runs the callback when the string matches the given shell-style pattern, in
which `*` stands for any run of characters.

```python title="examples/strings.py"
result = str_("almasix.pyi").when_is("*.py*", lambda s: s.upper()).value()

# 'ALMASIX.PYI'
```

### when_is_ascii

Runs the callback when the string encodes cleanly as ASCII. The test takes no
arguments.

```python title="examples/strings.py"
result = str_("ascii only").when_is_ascii(lambda s: s.upper()).value()

# 'ASCII ONLY'
```

### when_is_ulid

Runs the callback when the string has the shape of a ULID: 26 Crockford Base32
characters. The test takes no arguments.

```python title="examples/strings.py"
result = str_("01ARZ3NDEKTSV4RRFFQ69G5FAV").when_is_ulid(lambda s: s.take(10)).value()

# '01ARZ3NDEK'
```

### when_is_uuid

Runs the callback when the string parses as a UUID. The test takes no
arguments.

```python title="examples/strings.py"
result = str_("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11").when_is_uuid(lambda s: s.before("-")).value()

# 'a0eebc99'
```

### when_not_empty

Runs the callback when the string is not empty. The test takes no arguments.

```python title="examples/strings.py"
result = str_("ada").when_not_empty(lambda s: s.title()).value()

# 'Ada'

result = str_("").when_not_empty(lambda s: s.title()).value()

# ''
```

### when_not_exactly

Runs the callback when the string differs from the given value.

```python title="examples/strings.py"
result = str_("almasix").when_not_exactly("other", lambda s: s.append(" (kept)")).value()

# 'almasix (kept)'
```

### when_starts_with

Runs the callback when the string starts with the needle, or with any of them
when given an iterable.

```python title="examples/strings.py"
result = str_("/docs/strings").when_starts_with("/", lambda s: s.ltrim("/")).value()

# 'docs/strings'
```

### when_test

Runs the callback when the string matches the given regular expression, using
the same search as `test`.

```python title="examples/strings.py"
result = str_("order-4417").when_test(r"[0-9]+$", lambda s: s.after_last("-")).value()

# '4417'
```

### word_count

Counts the whitespace-separated words and returns an `int`, which ends the
chain.

```python title="examples/strings.py"
result = str_("one two three").word_count()

# 3
```

### word_wrap

Inserts the break string after every `characters` characters, counting
characters rather than finding word boundaries, so a break can land inside a
word.

```python title="examples/strings.py"
result = str_("The quick brown fox").word_wrap(10, "<br>").value()

# 'The quick <br>brown fox'
```

### words

Truncates to the first `words` whitespace-separated words and appends `end`,
which defaults to `...`; a shorter string is returned untouched.

```python title="examples/strings.py"
result = str_("one two three four").words(2).value()

# 'one two...'

result = str_("one two three four").words(2, " >>>").value()

# 'one two >>>'
```

### wrap

Surrounds the string with `before` and `after`, with `after` defaulting to
`before` so that a single argument wraps both ends with the same text. `unwrap`
reverses it.

```python title="examples/strings.py"
result = str_("almasix").wrap('"').value()

# '"almasix"'

result = str_("almasix").wrap("[", "]").value()

# '[almasix]'
```

## Related

- [Helpers](/helpers/) — `Arr`, `Number`, paths, and the miscellaneous functions
- [Collections](/collections/) — `collect()`, including `join` and `implode`
- [Localization](/localization/) — `__()` and pluralisation for translated strings
