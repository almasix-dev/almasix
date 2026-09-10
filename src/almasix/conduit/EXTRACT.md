# Extract checklist — almasix-dev/conduit

Conduit currently lives in-tree as ``src/almasix/conduit/`` (Signet-style).

When cutting ``almasix-dev/conduit``:

1. Publish a namespace package that still exposes ``almasix.conduit``.
2. Depend on published ``almasix``.
3. CI: ruff + pytest; PyPI on tag.
4. Keep signed update URLs + ``APP_BASE_PATH`` contract in smoke.
5. Point Starlight / README extract links here → there.
