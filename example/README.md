# Example project

This development-only project demonstrates domain-routed tenant databases.

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py create_tenant acme --name "Acme" --domain acme.localhost
uv run python manage.py runserver
```

Open `http://acme.localhost:8000/` for the tenant site and
`http://localhost:8000/admin/` for the public admin. Mutation views require a
shared Django login.

Development defaults are intentionally convenient but are not deployment
credentials. For a production check, provide at least:

```bash
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY='replace-with-a-long-random-production-secret' \
DJANGO_ALLOWED_HOSTS='example.com,.example.com' \
uv run python manage.py check --deploy
```
