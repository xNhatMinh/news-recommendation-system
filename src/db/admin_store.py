"""Two small tables: source settings/status and IDs of hidden articles."""
from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from src.db.db import engine

DEFAULT_SOURCES = {
    "vnexpress": ("VnExpress", "vnexpress.net"),
    "dantri": ("Dân trí", "dantri.com.vn"),
    "tuoitre": ("Tuổi Trẻ", "tuoitre.vn"),
    "vietnamnet": ("VietNamNet", "vietnamnet.vn"),
}


def init_admin_tables():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS news_sources (
                code VARCHAR(30) PRIMARY KEY,
                name VARCHAR(100) NOT NULL DEFAULT '',
                domain VARCHAR(255) NOT NULL DEFAULT '',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                status VARCHAR(20) NOT NULL DEFAULT 'idle',
                started_at DATETIME,
                finished_at DATETIME,
                new_articles INTEGER NOT NULL DEFAULT 0,
                error VARCHAR(200) NOT NULL DEFAULT ''
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS hidden_articles (
                article_id BIGINT PRIMARY KEY
            )
        """))
        columns = {column["name"] for column in inspect(connection).get_columns("news_sources")}
        if "name" not in columns:
            connection.execute(text("ALTER TABLE news_sources ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''"))
        if "domain" not in columns:
            connection.execute(text("ALTER TABLE news_sources ADD COLUMN domain VARCHAR(255) NOT NULL DEFAULT ''"))
    init_user_columns()
    for code, (name, domain) in DEFAULT_SOURCES.items():
        try:
            with engine.begin() as connection:
                source = connection.execute(
                    text("SELECT code, name, domain FROM news_sources WHERE code = :code"),
                    {"code": code},
                ).mappings().first()
                if source is None:
                    connection.execute(
                        text("INSERT INTO news_sources (code, name, domain) VALUES (:code, :name, :domain)"),
                        {"code": code, "name": name, "domain": domain},
                    )
                elif not source["name"] or not source["domain"]:
                    connection.execute(
                        text("UPDATE news_sources SET name = :name, domain = :domain WHERE code = :code"),
                        {"code": code, "name": name, "domain": domain},
                    )
        except IntegrityError:
            # Another backend process may have inserted the same default source.
            pass


def init_user_columns():
    """Upgrade existing user profiles; leave their data and current sessions intact."""
    uid_type = 'VARCHAR(128)'
    if engine.dialect.name == 'mysql':
        uid_type += ' CHARACTER SET ascii COLLATE ascii_bin'
    fields = {'is_active': 'BOOLEAN NOT NULL DEFAULT TRUE',
              'token_version': 'INTEGER NOT NULL DEFAULT 0',
              'firebase_uid': uid_type}
    with engine.begin() as connection:
        existing = {column['name'] for column in inspect(connection).get_columns('users')}
        for name, definition in fields.items():
            if name not in existing:
                try:
                    connection.execute(text(f'ALTER TABLE users ADD COLUMN {name} {definition}'))
                except DBAPIError:
                    # A concurrent startup may already have added the same column.
                    if name not in {c['name'] for c in inspect(connection).get_columns('users')}:
                        raise
        schema = inspect(connection)
        indexes = schema.get_indexes('users') + schema.get_unique_constraints('users')
        if not any(item['column_names'] == ['firebase_uid'] and item.get('unique', True) for item in indexes):
            try:
                connection.execute(text('CREATE UNIQUE INDEX uq_users_firebase_uid ON users (firebase_uid)'))
            except DBAPIError:
                if 'uq_users_firebase_uid' not in {item['name'] for item in inspect(connection).get_indexes('users')}:
                    raise


def set_user_active(user_id, active):
    """Change status and revoke previous sessions in the same transaction."""
    with engine.begin() as connection:
        if connection.execute(text('SELECT id FROM users WHERE id = :id'), {'id': user_id}).first() is None:
            return False
        connection.execute(text('''
            UPDATE users SET is_active = :active, token_version = token_version + 1
            WHERE id = :id AND is_active <> :active
        '''), {'id': user_id, 'active': active})
        if not active:
            connection.execute(text('DELETE FROM user_devices WHERE user_id = :id'), {'id': user_id})
    return True


def get_sources():
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT * FROM news_sources")).mappings().all()
        result = []
        for row in rows:
            name, domain = row["name"], row["domain"]
            count = connection.execute(text("SELECT COUNT(*) FROM articles WHERE url LIKE :prefix"),
                                       {"prefix": f"https://{domain}/%"}).scalar()
            result.append({**dict(row), "enabled": bool(row["enabled"]), "name": name,
                           "domain": domain, "article_count": count})
    return result


def get_source(code):
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT code, name, domain, enabled FROM news_sources WHERE code = :code"),
            {"code": code},
        ).mappings().first()
    return dict(row) if row is not None else None


def set_source_enabled(code, enabled):
    with engine.begin() as connection:
        connection.execute(text("UPDATE news_sources SET enabled = :enabled WHERE code = :code"),
                           {"enabled": enabled, "code": code})


def source_started(code):
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE news_sources
            SET status = :status, started_at = :started_at, finished_at = NULL,
                new_articles = 0, error = ''
            WHERE code = :code
        """), {"status": "running", "started_at": datetime.now(), "code": code})


def source_finished(code, count=0, error=""):
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE news_sources
            SET status = :status, finished_at = :finished_at,
                new_articles = :new_articles, error = :error
            WHERE code = :code
        """), {"status": "failed" if error else "finished",
               "finished_at": datetime.now(), "new_articles": count,
               "error": error[:200], "code": code})


def set_article_hidden(article_id, hidden):
    with engine.begin() as connection:
        if connection.execute(text("SELECT id FROM articles WHERE id = :id"), {"id": article_id}).first() is None:
            return False
        if hidden:
            exists = connection.execute(
                text("SELECT article_id FROM hidden_articles WHERE article_id = :article_id"),
                {"article_id": article_id},
            ).first()
            if exists is None:
                connection.execute(
                    text("INSERT INTO hidden_articles (article_id) VALUES (:article_id)"),
                    {"article_id": article_id},
                )
        else:
            connection.execute(text("DELETE FROM hidden_articles WHERE article_id = :article_id"),
                               {"article_id": article_id})
    return True
