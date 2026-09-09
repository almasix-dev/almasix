# Deploy sketch

Minimal container layout for an Almasix **application** (not the framework
source tree). Copy these files next to a project created with `almasix new`,
adjust dependency install to match how you pin packages, then:

```bash
docker compose up --build
```

See the Starlight **Deployment** page for bare-metal, env, health checks,
`smith serve --workers`, and how framework releases are cut.
