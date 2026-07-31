# Triumphant Assemblies of God (TAG) — Church Website & Admin Platform

A full-featured church website and management platform for **Triumphant Assemblies of God**, Accra, Ghana — built with **Flask**, **MySQL**, and **Bootstrap 5**. Beyond the public site, it includes a role-based admin dashboard, member accounts, online giving via Paystack, daily devotionals, an e-book reading list, live-stream toggling, and a searchable blog.

> *A Place of Triumph, Love & Purpose.*

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Data Model](#data-model)
- [Roles & Permissions](#roles--permissions)
- [Routes Reference](#routes-reference)
- [Architecture Notes](#architecture-notes)
- [Security](#security)
- [Performance](#performance)
- [Deployment](#deployment)
- [Contributing / Conventions](#contributing--conventions)

---

## Overview

This isn't just a marketing site — it's a small CMS purpose-built for one church, with three cooperating pieces:

1. **Public website** — home, about, ministries, sermons, events, a searchable blog (devotionals / worship & leadership e-books / testimonies), contact, and online giving.
2. **Admin dashboard** — a role-gated back office for managing everything the public site displays: sermons, devotions, e-books, giving records, live-stream status, members, and other admin accounts.
3. **Member accounts** — a lightweight public-facing account system (separate from admin) so members can log in, manage their profile/avatar, and view their own giving history.

## Features

### Public site
- Home, About (leadership bios), Ministries, Events pages
- **Sermons** — video (YouTube-embedded) and audio (uploaded, single-track playback) archives
- **Blog** — daily devotion (with a 60-entry rolling archive), a curated Worship/Leadership e-book reading list with cover thumbnails, and member testimonies
- **Unified blog search** — one search box (in the blog sidebar) that free-text searches devotionals, e-books, and testimonies at once, or lists an entire category when you type its name (`worship`, `leadership`, `devotional`, `testimonials`)
- **Online giving** via Paystack (tithe, offering, missions, building fund, other)
- Contact page with a keyless Google Maps embed + "Get Directions" (browser geolocation)
- Member registration/login, profile page with avatar upload and paginated donation history

### Admin dashboard
- Stats overview (members, donations, prayer requests, messages, newsletter subscribers, devotions) with Chart.js trend/growth charts
- CRUD for video sermons, audio sermons, devotions, e-books (with cover thumbnail upload), members (soft delete)
- Giving overview with type/status filtering and per-type totals
- Live-stream on/off toggle (drives a homepage banner)
- Prayer requests, contact messages, and newsletter subscriber lists (read-only)
- **Developer-only**: manage other admin/pastor/developer accounts (reset passwords, update profile photos), full login audit history

### Auth & accounts
- Three admin-side roles — **Admin**, **Pastor**, **Developer** — sharing one dashboard, with Developer additionally getting account management and login-history access
- Separate **Member** accounts for the public site (own login/register/profile/password-reset flow)
- CSRF protection on every form, rate-limited login/registration/password-reset/contact endpoints, and a shorter idle session timeout for admin sessions than member sessions

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Flask 2.3 (application-factory pattern) |
| ORM | Flask-SQLAlchemy, MySQL via PyMySQL (installed as a `MySQLdb` drop-in) |
| Auth | Flask-Login (dual Admin/Member session), Flask-WTF (CSRF + forms) |
| Caching | Flask-Caching (in-memory in dev, Redis in production) |
| Rate limiting | Flask-Limiter |
| Security headers | Flask-Talisman (CSP, HSTS) |
| Compression | Flask-Compress |
| Payments | Paystack, called directly via `requests` (no SDK) |
| Frontend | Jinja2, Bootstrap 5, vanilla JS, Chart.js (admin charts, via CDN) |
| Schema bootstrap | `init_db.py` — hand-written, additive-only SQL (no Alembic/Flask-Migrate) |

Theme: gold (`#C8973A`) and royal blue (`#0D2B6B`), Cormorant Garamond (display) + Nunito (body) — see the CSS custom properties in `app/static/css/style.css`.

## Project Structure

```
Triumphant_Assemblies_of_God/
├── app/
│   ├── __init__.py          # App factory: extensions, blueprints, CSP, error handlers
│   ├── models.py             # SQLAlchemy models (mirrors init_db.py by hand)
│   ├── routes.py             # Public site + JSON API (main_bp, api_bp)
│   ├── admin.py               # Admin dashboard (admin_bp, /admin)
│   ├── auth.py                # Member auth (auth_bp, /members)
│   ├── forms.py               # Flask-WTF form classes
│   ├── decorators.py          # @admin_required / @member_required / @developer_required
│   ├── utils.py                # Sanitization, file-type validation, cached query helpers
│   ├── email_utils.py          # Pluggable password-reset email (SMTP or dev log/flash)
│   ├── templates/
│   │   ├── base.html            # Public layout (nav, footer, meta/OG/JSON-LD)
│   │   ├── public/                # Public pages + shared macros (_devotion_card, _ebook_card, _testimony_card)
│   │   ├── admin/                  # Admin dashboard templates
│   │   └── auth/                    # Member auth templates
│   └── static/
│       ├── css/style.css             # Theme + all component styles
│       ├── js/main.js                 # Public site JS (nav, search UX, sermon filter, etc.)
│       ├── js/admin.js                  # Admin dashboard JS (sidebar, charts, count-up)
│       └── uploads/                       # User-uploaded files (git-ignored): avatars/ ebooks/ ebook_thumbnails/ audio/
├── config.py                # Config classes: Development / Production / Testing
├── init_db.py                # Canonical schema bootstrap (additive only, idempotent)
├── run.py                     # Dev entrypoint (`python run.py`)
├── requirements.txt            # Python dependencies — kept in sync with every install
├── .env.example                 # Template for local .env
├── CLAUDE.md                     # AI-assistant-facing architecture & ground rules
└── .claude/                       # Claude Code hooks (blocks DROP/TRUNCATE SQL)
```

## Getting Started

### Prerequisites
- Python 3.9+
- MySQL 5.7+ (or MariaDB equivalent) running locally
- (Optional, production only) Redis, for shared caching/rate-limit storage across workers

### 1. Clone and set up a virtual environment
```bash
git clone <repo-url>
cd Triumphant_Assemblies_of_God
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment variables
```bash
cp .env.example .env
```
Edit `.env` with your real MySQL credentials, and (optionally) Paystack test keys and SMTP settings. See [Environment Variables](#environment-variables) below for the full list.

### 4. Initialize the database
```bash
python init_db.py
```
This creates the database and all tables if they don't exist, adds any missing columns to existing tables (safe to re-run any time), seeds a starter Worship/Leadership reading list and sample testimonies, and creates the three default accounts (Admin/Developer/Pastor) from your `.env` — skipping any that already exist.

### 5. Run the app
```bash
python run.py
```
Visit `http://localhost:5000`. Admin dashboard: `http://localhost:5000/admin/login`. Member login: `http://localhost:5000/members/login`.

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session signing key — use a long random string in production |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DB` | Yes | Database connection |
| `FLASK_ENV` | No | `development` (default) / `production` / `testing` — selects the config class |
| `PAYSTACK_SECRET_KEY` / `PAYSTACK_PUBLIC_KEY` | For giving | Without these, giving initialization still creates a pending record but verification will 503 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | No | Real email delivery for password resets. Unset in dev — reset links are logged and flashed instead |
| `ADMIN_DEFAULT_*` / `DEVELOPER_DEFAULT_*` / `PASTOR_DEFAULT_*` | No | Seed credentials for the three default accounts (`init_db.py`); each has a hardcoded fallback if omitted |
| `REDIS_URL` | Production only | Shared cache + rate-limit storage across workers |

See `.env.example` for the complete, ready-to-copy template.

## Data Model

All tables live in `init_db.py` (canonical, additive-only DDL) and are mirrored by hand in `app/models.py`.

| Table | Purpose |
|---|---|
| `admins` | Admin/Developer/Pastor accounts (`role` column distinguishes them) |
| `admin_login_logs` | Login audit trail (developer-only view) |
| `members` | Public member accounts (soft-deletable via `is_active_member`) |
| `video_sermons` / `audio_sermons` | Sermon archive (YouTube URL vs. uploaded file) |
| `devotions` | Daily devotion — one per day, rolling 60-entry cap |
| `ebooks` | Worship/Leadership reading list (title, author, summary, optional PDF + cover thumbnail) |
| `testimonies` | Member testimonies |
| `live_stream_settings` | Singleton row toggling the homepage live-stream banner |
| `giving` | Donation records, extended with Paystack reference/status/member link |
| `prayer_requests` / `contact_messages` / `newsletter_subscribers` | Public form submissions |

**No table is ever `DROP`ped or `TRUNCATE`d** — enforced by a Claude Code hook (see `.claude/settings.json`). Deletes are single-record (soft delete where a row might be referenced elsewhere, e.g. members with donation history); the devotion 60-cap prune is a single bounded `DELETE ... WHERE id IN (...)`, never a loop or a wipe.

## Roles & Permissions

| Role | Dashboard access | Exclusive to this role |
|---|---|---|
| **Admin** | Full dashboard (members, sermons, devotions, e-books, giving, live stream, prayer requests, messages, newsletter) | — |
| **Pastor** | Same as Admin | — |
| **Developer** | Same as Admin | My Profile, Manage Admins (reset any admin's password/avatar), full Login History |
| **Member** | None (public site only) | Own profile, avatar, donation history |

All three admin-side roles are seeded once by `init_db.py`; there's no in-app UI to create a new admin account or change a role — that's intentional (see `CLAUDE.md`).

## Routes Reference

### Public (`main_bp`)
`/`, `/about`, `/ministries`, `/sermons`, `/events`, `/blog`, `/blog/devotionals`, `/blog/worship`, `/blog/leadership`, `/blog/testimonies`, `/blog/search?q=`, `/contact`, `/giving`, `/robots.txt`, `/sitemap.xml`

### Public JSON API (`api_bp`, prefix `/api`) — all rate-limited
`POST /prayer-request`, `POST /contact-form`, `POST /newsletter`, `POST /giving/init`, `POST /paystack/verify`

### Member auth (`auth_bp`, prefix `/members`)
`/register`, `/login`, `/logout`, `/profile`, `/forgot-password`, `/reset-password/<token>`

### Admin dashboard (`admin_bp`, prefix `/admin`)
`/login`, `/logout`, `/profile`*, `/accounts`*, `/accounts/<id>/edit`*, `/forgot-password`, `/reset-password/<token>`, `/dashboard`, `/login-history`*, `/api/chart-data`, `/live-stream`, `/members`, `/members/add`, `/members/<id>/edit`, `/members/<id>/delete`, `/members/<id>`, `/sermons/video`, `/sermons/video/add`, `/sermons/video/<id>/edit`, `/sermons/video/<id>/delete`, `/sermons/audio` (+ add/edit/delete), `/devotions` (+ add/edit), `/ebooks` (+ add/edit/delete), `/giving`, `/prayer-requests`, `/messages`, `/newsletter-subscribers`

\* Developer-only.

## Architecture Notes

- **Dual auth, one login manager**: `Admin` and `Member` are separate model classes sharing one `flask_login.LoginManager` via a compound session ID (`"admin:<id>"` / `"member:<id>"`). See `CLAUDE.md` for why they aren't merged into one `User(role)` table.
- **Schema bootstrap, not migrations**: `init_db.py` is a standalone, idempotent script — `CREATE TABLE IF NOT EXISTS` plus an `add_column_if_missing()` helper for additive `ALTER TABLE`s. No Alembic/Flask-Migrate. Run it again any time you pull schema changes.
- **Paystack flow**: `/api/giving/init` creates a `pending` record server-side (never trusting a client-supplied "already paid" claim); Paystack's Inline JS collects payment client-side; `/api/paystack/verify` confirms with Paystack's REST API before ever marking a donation `completed`.
- **Caching**: Flask-Caching is wired to cache *data fetches* (e.g. e-book/testimony queries, the admin chart-data endpoint, `robots.txt`/`sitemap.xml`) rather than full pages — every page has a CSRF-bearing form in the footer, so whole-page caching would leak one visitor's CSRF token to everyone else served that cached copy. E-book cache is invalidated immediately on add/edit/delete.
- **SEO**: per-page meta description/canonical/Open Graph/Twitter Card tags, JSON-LD `Church` structured data, and a dynamically generated `sitemap.xml`/`robots.txt` — all built from `request.url_root` so they're correct on any domain without code changes.

## Security

- CSRF protection (Flask-WTF) on every POST route/form
- Rate limiting (Flask-Limiter) on login, registration, password reset, and public form endpoints
- File uploads validated by magic bytes (not just extension) and capped per type (2MB avatars/e-book covers, 10MB PDFs, plus a 16MB global request ceiling)
- Security headers via Flask-Talisman (CSP, HSTS in production)
- Admin sessions get a 30-minute idle timeout; member sessions last 7 days
- **No code may ever `DROP`/`TRUNCATE` a table** — enforced by a Claude Code hook; see `CLAUDE.md`
- **Every installed dependency must be added to `requirements.txt` in the same change** — also enforced as a hard rule in `CLAUDE.md`

## Performance

- Flask-Compress for response compression
- Static assets cached for 30 days in production (`SEND_FILE_MAX_AGE_DEFAULT`)
- Cached, invalidation-aware data-layer queries for e-books/testimonies/chart-data (see Architecture Notes)

## Deployment

Set `FLASK_ENV=production` and provide production `MYSQL_*`/`REDIS_URL` values. Run behind Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```

`ProductionConfig` (in `config.py`) automatically switches to Redis-backed caching/rate-limiting, forces HTTPS, and enables secure session cookies.

## Contributing / Conventions

Read **`CLAUDE.md`** before making changes — it documents the real architecture (this README is the human-facing summary; `CLAUDE.md` is the detailed, AI-assistant-facing source of truth) and two hard rules: never `DROP`/`TRUNCATE` a table, and always add a newly installed package to `requirements.txt` in the same change.

---

**Triumphant Assemblies of God** — Accra, Ghana. *A Place of Triumph, Love & Purpose.*
