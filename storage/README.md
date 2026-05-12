# storage/

Local bind-mounts for dev convenience. **Gitignored** — contents are ephemeral.

## Layout

```
storage/
├── minio/      # MinIO data dir bind-mount (dev only)
└── postgres/   # Postgres data dir bind-mount (dev only)
```

## Hard rules

- In production, replace these bind-mounts with named Docker volumes or external managed storage. Don't run prod data out of `./storage/`.
- Never commit anything under here. If you find yourself wanting to commit a file, it belongs somewhere else.
- Reset with `make down && docker volume rm aivideo_postgres aivideo_minio aivideo_redis` (only when intentional — this is destructive).
