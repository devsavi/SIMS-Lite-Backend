# Alembic Migration Versions

Migration scripts are generated automatically by Alembic.

To generate a new migration after modifying ORM models:

```bash
alembic revision --autogenerate -m "describe your changes"
```

To apply all pending migrations:

```bash
alembic upgrade head
```

To roll back one revision:

```bash
alembic downgrade -1
```
