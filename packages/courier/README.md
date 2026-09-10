# Courier

In-repo first-party-style package that exercises Almasix's package development
API (M29): config merge, route loading, namespaced views, translations,
migration path registration, and publish tags.

## Install

From the repository root:

```bash
pip install -e packages/courier
```

Or list the provider explicitly in `config/app.py` and put
`packages/courier/src` on `PYTHONPATH`.

## Publish

```bash
smith vendor:publish --tag=courier-config
```
