# NyasaBlog

A web platform dedicated to promoting positive content created by Malawian content creators and influencers. NyasaBlog aims to be the most trusted source for Malawian content in the areas of Culture, Entertainment, Entrepreneurship, and more.

## About

NyasaBlog was created and founded by **Ephraim Kanyandula**, a Malawian national, with the vision of building a platform that amplifies Malawian voices and showcases the best of Malawian creativity and innovation.

**Live site:** [nyasablog.com](https://nyasablog.com)

## Tech Stack

- **Backend:** Django 5.2 LTS, Django REST Framework
- **Database:** SQLite (development), PostgreSQL (planned for production)
- **Storage:** DigitalOcean Spaces (S3-compatible)
- **Server:** Gunicorn + Nginx on DigitalOcean
- **Frontend:** Django Templates, Bootstrap
- **Auth:** Custom user model with token-based API authentication

## Project Structure

```
nyasablog/
├── mysite/          # Project settings and root URL config
├── personal/        # Home, about, contact pages
├── account/         # Custom user model, registration, auth
│   └── api/         # Account REST API endpoints
├── blog/            # Blog posts CRUD
│   └── api/         # Blog REST API endpoints
├── templates/       # Base templates, shared snippets
└── static/          # Static assets
```

## Local Development Setup

### Prerequisites

- Python 3.12+
- pip

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd nyasablog

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create local settings
cp settings.ini.example settings.ini
# Edit settings.ini with your local config

# Run migrations
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

Visit [http://127.0.0.1:8000](http://127.0.0.1:8000)

## API Endpoints

### Blog API
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/blog/list` | List all posts |
| GET | `/api/blog/<slug>/` | Get post details |
| POST | `/api/blog/create` | Create a post |
| PUT | `/api/blog/<slug>/update` | Update a post |
| DELETE | `/api/blog/<slug>/delete` | Delete a post |

### Account API
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/account/register` | Register |
| POST | `/api/account/login` | Get auth token |
| GET | `/api/account/properties` | Get user info |
| PUT | `/api/account/properties/update` | Update user info |

## Author

**Ephraim Kanyandula** — Creator & Founder

## License

All rights reserved.
