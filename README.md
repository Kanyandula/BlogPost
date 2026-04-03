# NyasaBlog

A digital platform dedicated to promoting positive content created by Malawian content creators and influencers. NyasaBlog aims to be the most trusted source for Malawian content in the areas of Culture, Entertainment, Entrepreneurship, Tourism, Technology, Sports, Lifestyle, Education, Health, and Opinion.

**Live site:** [nyasablog.com](https://nyasablog.com)

## About

NyasaBlog was created and founded by **Ephraim Kanyandula**, a Malawian national, with the vision of building a platform that amplifies Malawian voices and showcases the best of Malawian creativity and innovation.

## Features

- **Blog Posts** — Create, edit, delete with rich text editor (CKEditor 5), featured images, draft/publish workflow
- **Categories & Tags** — 10 Malawian-focused categories, free-form tags for content organization
- **Comments** — Threaded comments with one level of replies
- **Likes & Bookmarks** — Like posts and save them for later reading
- **User Profiles** — Bio, avatar, location, social links (Twitter, Facebook, Instagram, LinkedIn)
- **Author Pages** — Public profile with post grid and stats
- **Search** — Dedicated search page with category filtering and related topics
- **Social Sharing** — WhatsApp (priority), Facebook, Twitter/X, Copy Link with Open Graph meta tags
- **Dark Mode** — Toggle with system preference detection and localStorage persistence
- **Responsive Design** — Mobile-first with bottom navigation bar and floating action button
- **REST API** — Full API for all features with token authentication

## Tech Stack

- **Backend:** Django 5.2 LTS, Django REST Framework 3.17
- **Frontend:** Tailwind CSS (CDN), Inter font, Material Symbols icons
- **Design System:** "The Modern Savanna Editorial" — see [DESIGN.md](DESIGN.md)
- **Rich Text:** CKEditor 5
- **Database:** SQLite
- **Storage:** DigitalOcean Spaces (S3-compatible, production)
- **Server:** Gunicorn 25.3 + Nginx on DigitalOcean (Ubuntu, Python 3.12)
- **Auth:** Custom user model with token-based API authentication

## Project Structure

```
nyasablog/
├── mysite/              # Settings, root URLs, WSGI
├── personal/            # Home, about, contact, search, API docs
│   └── templates/
├── account/             # Custom user model, profiles, auth views
│   ├── api/             # Account REST API
│   └── templates/
├── blog/                # Posts, categories, tags, comments, likes, bookmarks
│   ├── api/             # Blog REST API
│   └── templates/
├── templates/           # Base template, header, footer, 404, registration
├── static/              # Static assets (logo)
├── DESIGN.md            # Design system documentation
└── requirements.txt
```

## Local Development Setup

### Prerequisites

- Python 3.12+
- pip

### Installation

```bash
git clone https://github.com/Kanyandula/BlogPost.git
cd BlogPost

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp settings.ini.example settings.ini
# Edit settings.ini with your SECRET_KEY and DEBUG=True

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Running Tests

```bash
python manage.py test blog
```

55 tests covering models, views, auth, and API.

## REST API

All authenticated endpoints require `Authorization: Token <token>` header.

### Blog API

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/blog/list` | Yes | List posts (search, filter, paginate) |
| GET | `/api/blog/<slug>/` | Yes | Get post detail |
| POST | `/api/blog/create` | Yes | Create post |
| PUT | `/api/blog/<slug>/update` | Yes | Update post (author only) |
| DELETE | `/api/blog/<slug>/delete` | Yes | Delete post (author only) |
| GET | `/api/blog/categories/` | No | List all categories |
| GET | `/api/blog/tags/` | No | List all tags |
| GET | `/api/blog/<slug>/comments/` | No | List threaded comments |
| POST | `/api/blog/<slug>/comments/create/` | Yes | Create comment |
| DELETE | `/api/blog/comments/<pk>/delete/` | Yes | Delete own comment |
| POST | `/api/blog/<slug>/like/` | Yes | Toggle like |
| POST | `/api/blog/<slug>/bookmark/` | Yes | Toggle bookmark |
| GET | `/api/blog/bookmarks/` | Yes | List bookmarked posts |

**List filtering:** `?category=<slug>`, `?status=published`, `?search=<query>`, `?ordering=-date_updated`

### Account API

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/account/register` | No | Register new user |
| POST | `/api/account/login` | No | Get auth token |
| GET | `/api/account/properties` | Yes | Get user info |
| PUT | `/api/account/properties/update` | Yes | Update user info |
| PUT | `/api/account/change_password/` | Yes | Change password |
| GET | `/api/account/profile/<username>/` | No | Public author profile |
| PUT | `/api/account/profile/update/` | Yes | Update own profile |

Full API documentation available at [nyasablog.com/api/](https://nyasablog.com/api/)

## Author

**Ephraim Kanyandula** — Creator & Founder

## License

All rights reserved.
