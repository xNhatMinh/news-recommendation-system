# News Recommendation System

A FastAPI backend for collecting Vietnamese news, storing articles, generating multilingual embeddings, and serving personalized recommendations and related features.

## Features

- Crawls articles from VnExpress, Dân Trí, Tuổi Trẻ, and VietNamNet.
- Generates sentence embeddings for semantic search and recommendations.
- Provides authentication through Firebase and issues backend JWT access tokens.
- Supports user preferences, reading history, bookmarks, notifications, and device registration.
- Uses Gemini for article summaries and term explanations.
- Includes an admin page and protected endpoints for managing sources, users, articles, and news updates.

## Tech stack

- Python, FastAPI, and Uvicorn
- MySQL through SQLAlchemy and PyMySQL
- Sentence Transformers and scikit-learn
- Firebase Admin SDK
- Google Gemini API

## Requirements

- Python 3.10 or newer
- MySQL server and an application database
- Firebase project credentials (for authentication and Firebase services)
- Gemini API key (for summaries and term explanations)

The database must contain the core `users` and `articles` tables, along with the other tables used by enabled features. On API startup, the app creates its admin tables and adds required Firebase/admin fields to `users`; it does not create the complete application schema from scratch.

## Setup

Run these commands from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a `.env` file in the repository root. Use your own credentials; do not commit this file.

```dotenv
# MySQL connection
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=news_recommendation

# Required by the API's JWT authentication
JWT_SECRET_KEY=replace_with_a_long_random_secret

# Firebase Authentication Web API
FIREBASE_WEB_API_KEY=your_firebase_web_api_key

# Google Gemini
GEMINI_API_KEY=your_gemini_api_key

# Required by the protected internal news-update endpoints
N8N_KEY=replace_with_a_private_update_key

# Optional: needed for the admin login
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=generated_password_hash
```

Place the Firebase Admin service account JSON at the repository root as `firebase-service-account.json`. The application expects that exact path. Keep it private and never commit it.

`GEMINI_TERM_MODEL` and `GEMINI_MODEL` can optionally select a term-explanation model. If unset, term explanations use `gemini-3.5-flash-lite`; article summaries currently use `gemini-3.5-flash-lite` in code.

## Run the API

```powershell
uvicorn src.api.main:app --reload
```

By default, the server is available at `http://127.0.0.1:8000`.

- Health check: `GET /health`
- Interactive API documentation: `GET /docs`
- Admin page: `GET /admin`

The API initializes its admin tables during startup, so a valid MySQL configuration and the expected existing database schema are needed before it can serve requests.
