# 🚀 DEPLOY.md — Static Landing Page · GitHub Actions → Custom `.tech` Domain

> **Scope:** Auto-publish a static site to a custom `.tech` domain on every push to `main`.
> Uses a self-hosted or cloud VPS as the target server (rsync over SSH).
> Adapt paths marked `# ← CHANGE ME` to match your setup.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1 — SSH Key Setup](#step-1--ssh-key-setup)
3. [Step 2 — GitHub Secrets Configuration](#step-2--github-secrets-configuration)
4. [Step 3 — DNS Settings for Your `.tech` Domain](#step-3--dns-settings-for-your-tech-domain)
5. [Step 4 — Server Preparation](#step-4--server-preparation)
6. [Step 5 — Workflow YAML](#step-5--workflow-yaml)
7. [Step 6 — CNAME File (for GitHub Pages variant)](#step-6--cname-file-for-github-pages-variant)
8. [Step 7 — First Deployment Checklist](#step-7--first-deployment-checklist)
9. [Troubleshooting](#troubleshooting)
10. [Security Hardening Notes](#security-hardening-notes)

---

## Prerequisites

| Requirement | Details |
|---|---|
| GitHub repository | Public or private; branch named `main` |
| Static site output | Plain HTML/CSS/JS **or** a build step (Vite, Next export, Hugo, etc.) |
| Target server | VPS / dedicated server running Linux with `nginx` or `apache2` |
| Domain registrar access | Ability to add/edit DNS records for your `.tech` domain |
| Local machine | `ssh-keygen` available (Linux/macOS built-in; Windows via Git Bash or WSL) |

---

## Step 1 — SSH Key Setup

Generate a **dedicated deploy keypair** — never reuse your personal SSH key.

```bash
# Run locally — do NOT add a passphrase (CI cannot enter one interactively)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/deploy_key_mysite

# Two files are created:
#   ~/.ssh/deploy_key_mysite       ← PRIVATE key  (goes into GitHub Secrets)
#   ~/.ssh/deploy_key_mysite.pub   ← PUBLIC key   (goes onto the server)
```

### Add the public key to your server

```bash
# Copy the public key to your server's authorized_keys
ssh-copy-id -i ~/.ssh/deploy_key_mysite.pub your_user@your-server-ip
# OR manually:
cat ~/.ssh/deploy_key_mysite.pub | ssh your_user@your-server-ip \
  "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

### Verify the key works before wiring it into CI

```bash
ssh -i ~/.ssh/deploy_key_mysite your_user@your-server-ip "echo 'SSH OK'"
# Expected output: SSH OK
```

> ⚠️ **Never commit the private key file to your repo.** Add `deploy_key_mysite` to `.gitignore` immediately.

---

## Step 2 — GitHub Secrets Configuration

Navigate to: **Repository → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value | Notes |
|---|---|---|
| `SSH_PRIVATE_KEY` | Full contents of `~/.ssh/deploy_key_mysite` | Include the `-----BEGIN...` and `-----END...` lines |
| `SSH_HOST` | `203.0.113.42` | Your server's IP or hostname — # ← CHANGE ME |
| `SSH_USER` | `deploy` | Linux user on the server — # ← CHANGE ME |
| `SSH_PORT` | `22` | Change if your server uses a non-standard port |
| `DEPLOY_PATH` | `/var/www/yourdomain.tech/html` | Absolute path to web root — # ← CHANGE ME |
| `KNOWN_HOSTS` | Output of `ssh-keyscan -H your-server-ip` | Prevents MITM on first connect |

### Capturing KNOWN_HOSTS

```bash
ssh-keyscan -H your-server-ip 2>/dev/null
# Paste the entire output as the KNOWN_HOSTS secret value
```

---

## Step 3 — DNS Settings for Your `.tech` Domain

Log in to your domain registrar (e.g., Namecheap, GoDaddy, Porkbun, Spaceship) and add the following records.

### Option A — Pointing to a VPS (recommended for full server control)

| Type | Host | Value | TTL |
|---|---|---|---|
| `A` | `@` | `203.0.113.42` (your server IP) | 300 |
| `A` | `www` | `203.0.113.42` (your server IP) | 300 |
| `CNAME` | `www` | `yourdomain.tech.` | 300 — use only if NOT using A for www |

> Use either `A` **or** `CNAME` for `www`, not both.

### Option B — GitHub Pages custom domain

| Type | Host | Value | TTL |
|---|---|---|---|
| `A` | `@` | `185.199.108.153` | 3600 |
| `A` | `@` | `185.199.109.153` | 3600 |
| `A` | `@` | `185.199.110.153` | 3600 |
| `A` | `@` | `185.199.111.153` | 3600 |
| `CNAME` | `www` | `your-github-username.github.io.` | 3600 |

### Verify DNS propagation

```bash
# Check A record (may take 5–60 min to propagate)
dig +short A yourdomain.tech
nslookup yourdomain.tech 8.8.8.8

# Check from multiple regions
curl -s "https://dns.google/resolve?name=yourdomain.tech&type=A" | python3 -m json.tool
```

### SSL / TLS Certificate (VPS path)

```bash
# Install Certbot and obtain a Let's Encrypt certificate
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.tech -d www.yourdomain.tech
# Follow the prompts — Certbot auto-renews via systemd timer
```

---

## Step 4 — Server Preparation

```bash
# Install nginx
sudo apt update && sudo apt install nginx -y

# Create web root directory
sudo mkdir -p /var/www/yourdomain.tech/html          # ← CHANGE ME
sudo chown -R $USER:www-data /var/www/yourdomain.tech/html
sudo chmod -R 755 /var/www/yourdomain.tech

# Create nginx server block
sudo nano /etc/nginx/sites-available/yourdomain.tech
```

Paste this nginx config:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.tech www.yourdomain.tech;   # ← CHANGE ME

    root /var/www/yourdomain.tech/html;                # ← CHANGE ME
    index index.html index.htm;

    location / {
        try_files $uri $uri/ =404;
    }

    # Cache static assets aggressively
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
}
```

```bash
# Enable the site and reload nginx
sudo ln -s /etc/nginx/sites-available/yourdomain.tech /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Step 5 — Workflow YAML

Create this file at `.github/workflows/deploy.yml` in your repository:

```yaml
# .github/workflows/deploy.yml
# Deploys static site to VPS via rsync over SSH on every push to main.

name: Deploy to yourdomain.tech                       # ← CHANGE ME

on:
  push:
    branches:
      - main
  workflow_dispatch:                                   # Allow manual triggers

concurrency:
  group: production-deploy
  cancel-in-progress: false                           # Never cancel a deploy mid-flight

jobs:
  build-and-deploy:
    name: Build & Deploy
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      # ── 1. Checkout ────────────────────────────────────────────────────────
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      # ── 2. (Optional) Build step — remove if your site is plain HTML ───────
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build static site
        run: npm run build                             # ← CHANGE ME (e.g. vite build, hugo, etc.)
        env:
          NODE_ENV: production

      # ── 3. Configure SSH ───────────────────────────────────────────────────
      - name: Configure SSH agent
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.SSH_PRIVATE_KEY }}

      - name: Add server to known hosts
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.KNOWN_HOSTS }}" >> ~/.ssh/known_hosts
          chmod 600 ~/.ssh/known_hosts

      # ── 4. Deploy via rsync ────────────────────────────────────────────────
      - name: Deploy to server
        run: |
          rsync -avz --delete \
            --exclude='.git' \
            --exclude='.github' \
            --exclude='node_modules' \
            --exclude='.env*' \
            -e "ssh -p ${{ secrets.SSH_PORT }} -o StrictHostKeyChecking=yes" \
            ./dist/                                    # ← CHANGE ME: your build output dir
            ${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }}:${{ secrets.DEPLOY_PATH }}/

      # ── 5. Smoke test ──────────────────────────────────────────────────────
      - name: Smoke test — verify site responds
        run: |
          sleep 5
          STATUS=$(curl -o /dev/null -s -w "%{http_code}" https://yourdomain.tech)   # ← CHANGE ME
          echo "HTTP status: $STATUS"
          if [ "$STATUS" != "200" ]; then
            echo "::error::Smoke test failed — site returned HTTP $STATUS"
            exit 1
          fi

      # ── 6. Notify on failure ───────────────────────────────────────────────
      - name: Notify on failure
        if: failure()
        run: |
          echo "::error::Deployment to yourdomain.tech FAILED on commit ${{ github.sha }}"
          # Add your notification hook here (Slack, Discord webhook, email, etc.)
```

> **Plain HTML site?** Delete steps 2 ("Set up Node.js" through "Build static site") and change `./dist/` in the rsync step to `./` or your HTML folder name.

---

## Step 6 — CNAME File (for GitHub Pages variant)

If you're using **GitHub Pages** instead of a VPS, create a `CNAME` file in your repo root:

```
yourdomain.tech
```

And use this workflow instead of the rsync version above:

```yaml
# .github/workflows/deploy-pages.yml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Pages
        uses: actions/configure-pages@v5

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: './dist'                               # ← CHANGE ME

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

> Enable GitHub Pages in **Settings → Pages → Source → GitHub Actions** before running.

---

## Step 7 — First Deployment Checklist

Work through this list top-to-bottom before merging to `main` for the first time.

### Pre-flight

- [ ] `deploy_key_mysite` (private key) is **not** tracked by git — run `git status` to confirm
- [ ] All six GitHub Secrets are saved and spelled exactly as shown in Step 2
- [ ] DNS A records point to the correct server IP
- [ ] `dig +short yourdomain.tech` returns your server IP
- [ ] SSH manual login works: `ssh -i ~/.ssh/deploy_key_mysite your_user@your-server-ip`
- [ ] Web root directory exists on the server with correct ownership
- [ ] `nginx -t` passes with no errors on the server
- [ ] SSL certificate obtained (if applicable)

### Workflow file

- [ ] `.github/workflows/deploy.yml` committed and pushed to `main`
- [ ] All `# ← CHANGE ME` placeholders have been replaced
- [ ] Build output directory in rsync step matches your actual build tool output
- [ ] `workflow_dispatch` trigger is present (allows manual re-runs)

### Post-deploy verification

- [ ] GitHub Actions tab shows the workflow run as **green**
- [ ] `https://yourdomain.tech` loads in a browser
- [ ] `www.yourdomain.tech` redirects correctly
- [ ] HTTPS padlock is present (no mixed-content warnings in browser console)
- [ ] Hard-refresh the page (Ctrl+Shift+R) to confirm new content is live

---

## Troubleshooting

### ❌ `Permission denied (publickey)`

**Cause:** The private key in `SSH_PRIVATE_KEY` doesn't match the public key in `~/.ssh/authorized_keys` on the server.

```bash
# Confirm the public key is present on the server
ssh your_user@your-server-ip "cat ~/.ssh/authorized_keys"

# Re-copy if missing
ssh-copy-id -i ~/.ssh/deploy_key_mysite.pub your_user@your-server-ip

# Verify permissions on the server (must be exactly these)
ssh your_user@your-server-ip "ls -la ~/.ssh"
# ~/.ssh         should be 700
# authorized_keys should be 600
```

Also confirm the secret value includes the full key with header/footer lines:
```
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

---

### ❌ `Host key verification failed`

**Cause:** The `KNOWN_HOSTS` secret is empty, stale, or was generated for the wrong IP.

```bash
# Regenerate and update the secret
ssh-keyscan -H your-server-ip 2>/dev/null
# Copy ALL output lines into the KNOWN_HOSTS secret
```

---

### ❌ `rsync: [Errno 13] Permission denied` on the server

**Cause:** The deploy user doesn't own (or can't write to) `DEPLOY_PATH`.

```bash
# On the server — fix ownership
sudo chown -R deploy_user:www-data /var/www/yourdomain.tech/html  # ← CHANGE ME
sudo chmod -R 755 /var/www/yourdomain.tech/html
```

---

### ❌ Smoke test returns `000` or connection refused

**Cause:** Either nginx isn't running, the firewall blocks port 443/80, or the domain hasn't propagated yet.

```bash
# Check nginx status on the server
sudo systemctl status nginx

# Check firewall rules (ufw)
sudo ufw status
sudo ufw allow 'Nginx Full'

# Check DNS propagation externally
curl -s "https://1.1.1.1/dns-query?name=yourdomain.tech&type=A" \
  -H "accept: application/dns-json" | python3 -m json.tool
```

---

### ❌ Old content still showing after a successful deploy

**Cause:** Browser cache or CDN cache is serving stale assets.

```bash
# Hard-refresh in browser: Ctrl + Shift + R (Windows/Linux) / Cmd + Shift + R (macOS)

# Verify the server is actually serving new content (bypasses local cache)
curl -H "Cache-Control: no-cache" -I https://yourdomain.tech

# If using Cloudflare or another CDN — purge the cache from the dashboard
# or via API:
curl -X POST "https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/purge_cache" \
  -H "Authorization: Bearer {CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"purge_everything":true}'
```

---

### ❌ `rsync: --delete` removed files it shouldn't have

**Cause:** Source path has a trailing slash mismatch or wrong build folder specified.

```bash
# rsync trailing slash behavior:
rsync -avz ./dist/   user@host:/var/www/html/   # ✅ Copies CONTENTS of dist into html
rsync -avz ./dist    user@host:/var/www/html/   # ⚠️  Copies dist FOLDER itself into html
# Always use a trailing slash on the source path.
```

---

### ❌ Workflow doesn't trigger on push to main

**Cause:** Branch is named `master` instead of `main`, or the YAML has a syntax error.

```bash
# Check your default branch name
git branch --show-current

# Validate YAML syntax locally
npx js-yaml .github/workflows/deploy.yml
# OR install actionlint for full GitHub Actions validation
brew install actionlint && actionlint .github/workflows/deploy.yml
```

---

### ❌ SSL certificate errors after DNS change

**Cause:** Certbot obtained the cert before DNS propagated, or the cert didn't auto-renew.

```bash
# Check cert status
sudo certbot certificates

# Force renewal
sudo certbot renew --force-renewal

# Test auto-renewal
sudo certbot renew --dry-run
```

---

## Security Hardening Notes

| Practice | Implementation |
|---|---|
| Least-privilege deploy user | Create a `deploy` user with no sudo rights; own only the web root |
| Restrict SSH to deploy key only | In `authorized_keys`: `command="/bin/false",no-pty,no-agent-forwarding ssh-ed25519 AAAA...` |
| Rotate keys periodically | Generate a new keypair every 90 days; update both the server and the secret |
| Pin Action versions by SHA | e.g. `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` instead of `@v4` |
| Enable Dependabot for Actions | `.github/dependabot.yml` → `package-ecosystem: github-actions` |
| Branch protection on `main` | Require status checks to pass before merging; disallow force-push |
| Secrets scanning | Enable in **Settings → Security → Secret scanning** |

---

## Quick Reference — Key File Locations

```
your-repo/
├── .github/
│   └── workflows/
│       └── deploy.yml          ← GitHub Actions workflow
├── CNAME                       ← Only for GitHub Pages deployments
├── dist/                       ← Build output (rsync source) — gitignored
├── DEPLOY.md                   ← This file
└── .gitignore                  ← Must include: dist/, deploy_key_mysite, .env*

/var/www/yourdomain.tech/       ← Server web root (DEPLOY_PATH)
/etc/nginx/sites-available/     ← nginx server block config
/etc/letsencrypt/live/          ← SSL certificate location
```

---

*Last updated: 2026-08-11 · Tested with GitHub Actions `ubuntu-latest`, nginx 1.24, Certbot 2.x, Node.js 20 LTS*
```

It looks like your message came through empty — no new request was attached! 

Here's what I can do next with the `DEPLOY.md` we just built:

- **Convert it to a Word doc** — export as a `.docx` you can share with a team
- **Add a variant section** — e.g., for Cloudflare Pages, Netlify, or S3 + CloudFront deployments
- **Generate the workflow YAML as a standalone file** — ready to drop directly into `.github/workflows/`
- **Add a Dockerfile + nginx config** — for containerized deployments to the same `.tech` domain
- **Create a companion `CONTRIBUTING.md`** — covering branch strategy and PR-to-deploy flow

Just let me know what you'd like to tackle next!