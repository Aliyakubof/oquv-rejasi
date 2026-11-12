# Deployment (Ubuntu 22.04, PostgreSQL)

Deploys this Django app behind Gunicorn + Nginx. Another app on this VPS
already uses port 8000, so Gunicorn here binds to **127.0.0.1:8001** instead —
adjust if 8001 is also taken (`sudo ss -ltnp`).

No domain is assumed. Nginx listens on **port 8080** (also check it's free
with `sudo ss -ltnp`) with `server_name _;` — a catch-all that serves any
request regardless of hostname — so the app is reached at
`http://YOUR_VPS_IP:8080/`. This is a separate Nginx server block from
whatever serves the other app; it doesn't touch that config.

Replace `/srv/oquv_reja` and `YOUR_VPS_IP` below with your actual path and
server IP.

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git nginx postgresql postgresql-contrib libpq-dev
```

Skip `nginx` if it's already installed and running the other app. Skip
`postgresql` if this VPS already runs a Postgres server you'll reuse.

## 2. Get the code

```bash
sudo mkdir -p /srv/oquv_reja
sudo chown "$USER":"$USER" /srv/oquv_reja
git clone git@github.com:me-ilyos/oquv-reja.git /srv/oquv_reja
cd /srv/oquv_reja
git checkout main
```

## 3. Virtualenv and dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Database

Create the Postgres role and database:

```bash
sudo -u postgres psql -c "CREATE USER oquv_reja WITH PASSWORD 'replace-with-a-strong-password';"
sudo -u postgres psql -c "CREATE DATABASE oquv_reja OWNER oquv_reja;"
```

## 5. Environment file

`settings.py` reads `.env` via `django-environ`. Copy `.env.example` and fill
it in:

```bash
cp .env.example .env
```

```bash
cat > .env <<'EOF'
SECRET_KEY=replace-with-a-long-random-value
DEBUG=False
ALLOWED_HOSTS=YOUR_VPS_IP
CSRF_TRUSTED_ORIGINS=http://YOUR_VPS_IP:8080
HEMIS_API_KEY=replace-with-a-long-random-api-key
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SECURE_SSL_REDIRECT=False
DATABASE_URL=postgres://oquv_reja:replace-with-a-strong-password@localhost:5432/oquv_reja
EOF
chmod 600 .env
```

> **Note:** `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False`, and `SECURE_SSL_REDIRECT=False` are needed while serving over plain HTTP (`http://YOUR_VPS_IP:8080`). Remove those three lines once HTTPS/TLS is enabled in section 10 so `settings.py` enforces secure cookies and SSL redirect by default.

`CSRF_TRUSTED_ORIGINS` must include the full scheme + host + port you're
serving from (`http://YOUR_VPS_IP:8080`, not just the bare IP) — Django
checks login/POST requests' `Origin` header against this list separately
from `ALLOWED_HOSTS`, and rejects them with a 403 if it's missing.

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 6. Migrate, static files, superuser

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
mkdir -p media
```

## 7. Gunicorn systemd service

```bash
sudo tee /etc/systemd/system/oquv_reja.service > /dev/null <<'EOF'
[Unit]
Description=oquv_reja Gunicorn daemon
After=network.target

[Service]
User=YOUR_LINUX_USER
Group=www-data
WorkingDirectory=/srv/oquv_reja
ExecStart=/srv/oquv_reja/.venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8001 \
    oquv_reja.wsgi:application
Restart=on-failure
EnvironmentFile=/srv/oquv_reja/.env

[Install]
WantedBy=multi-user.target
EOF
```

Replace `YOUR_LINUX_USER` with the account that owns `/srv/oquv_reja`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now oquv_reja
sudo systemctl status oquv_reja
```

## 8. Nginx reverse proxy

Create a new server block file — it's independent of whatever config serves
the other app, so this won't disturb it:

```bash
sudo tee /etc/nginx/sites-available/oquv_reja > /dev/null <<'EOF'
server {
    listen 8080;
    server_name _;
    client_max_body_size 25M;

    location /static/ {
        alias /srv/oquv_reja/staticfiles/;
    }

    # Uploaded files are served only via Django authenticated views (FileResponse).
    # Keep /media/ internal so anonymous requests cannot download raw uploads.
    location /media/ {
        internal;
        alias /srv/oquv_reja/media/;
    }

    # Behind local Nginx, set TRUST_X_FORWARDED_FOR=True and TRUSTED_PROXY_IPS=127.0.0.1,::1 in .env
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/oquv_reja /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

`server_name _;` means "match any Host header" — there's no domain to match
against, so this block just handles everything that arrives on port 8080.
Visit `http://YOUR_VPS_IP:8080/` to confirm it's serving.

If you get a domain later, swap `server_name _;` for the real domain,
`listen 8080` back to `listen 80;`, and see the HTTPS note below.

## 9. Firewall

Nginx's new port needs to be reachable from outside; Gunicorn stays on
localhost.

```bash
sudo ufw allow 8080/tcp
sudo ufw status
```

Do **not** open port 8001 externally — only Nginx (8080) should be exposed.

## 10. HTTPS

Skipped for now — Let's Encrypt/certbot issues certificates for domain
names, not bare IPs, so TLS isn't available until you point a domain at
this server. Revisit this once you have one; at that point switch Nginx
back to port 80/443 and run `certbot --nginx -d your-domain`.

## 11. Deploying updates

```bash
cd /srv/oquv_reja
source .venv/bin/activate
git pull origin main
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart oquv_reja
```

## 12. Backups

Back up the database before every migration and on a schedule:

```bash
pg_dump -U oquv_reja -h localhost oquv_reja > /srv/oquv_reja/backups/db-$(date +%F).sql
```

Consider a cron job for this.
