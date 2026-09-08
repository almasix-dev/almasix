"""Loupe — what the REPL has waiting for you (`smith loupe`).

Your models under app/models are aliased automatically; everything here is
for the rest.
"""

config = {
    # Commands to have as callables in the shell: "inspire" → inspire().
    "commands": [],
    # Extra names to import, as name -> dotted path.
    "alias": {
        # "Str": "almasix.support.Str",
    },
    # Names to keep out of the shell, even if a model would have claimed them.
    "dont_alias": [],
}
