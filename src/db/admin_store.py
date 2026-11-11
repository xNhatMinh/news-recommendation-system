"""Two small tables: source settings/status and IDs of hidden articles."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, BigInteger, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from src.db.db import engine

SOURCES = {
    "vnexpress": ("VnExpress", "vnexpress.net"),
    "dantri": ("Dân trí", "dantri.com.vn"),
    "tuoitre": ("Tuổi Trẻ", "tuoitre.vn"),
    "vietnamnet": ("VietNamNet", "vietnamnet.vn"),
}
metadata = MetaData()
source_table = Table(
    "news_sources", metadata,
    Column("code", String(30), primary_key=True),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("status", String(20), nullable=False, default="idle"),
    Column("started_at", DateTime), Column("finished_at", DateTime),
    Column("new_articles", Integer, nullable=False, default=0),
    Column("error", String(200), nullable=False, default=""),
)
hidden_table = Table("hidden_articles", metadata, Column("article_id", BigInteger, primary_key=True))


def init_admin_tables():
    metadata.create_all(engine)
    init_user_columns()
    for code in SOURCES:
        try:
            with engine.begin() as connection:
                if connection.execute(select(source_table.c.code).where(source_table.c.code == code)).first() is None:
                    connection.execute(source_table.insert().values(code=code))
        except IntegrityError:
            # Another backend process may have inserted the same default source.
            pass


def init_user_columns():
    """Upgrade existing user profiles; leave their data and current sessions intact."""
    fields = {'is_active': 'BOOLEAN NOT NULL DEFAULT TRUE',
              'token_version': 'INTEGER NOT NULL DEFAULT 0'}
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
        rows = connection.execute(select(source_table)).mappings().all()
        result = []
        for row in rows:
            if row["code"] not in SOURCES:
                continue
            name, domain = SOURCES[row["code"]]
            count = connection.execute(text("SELECT COUNT(*) FROM articles WHERE url LIKE :prefix"),
                                       {"prefix": f"https://{domain}/%"}).scalar()
            result.append({**dict(row), "enabled": bool(row["enabled"]), "name": name,
                           "domain": domain, "article_count": count})
    result.sort(key=lambda row: list(SOURCES).index(row["code"]))
    return result


def set_source_enabled(code, enabled):
    with engine.begin() as connection:
        connection.execute(source_table.update().where(source_table.c.code == code).values(enabled=enabled))


def source_started(code):
    with engine.begin() as connection:
        connection.execute(source_table.update().where(source_table.c.code == code).values(
            status="running", started_at=datetime.now(), finished_at=None, new_articles=0, error=""))


def source_finished(code, count=0, error=""):
    with engine.begin() as connection:
        connection.execute(source_table.update().where(source_table.c.code == code).values(
            status="failed" if error else "finished", finished_at=datetime.now(),
            new_articles=count, error=error[:200]))


def set_article_hidden(article_id, hidden):
    with engine.begin() as connection:
        if connection.execute(text("SELECT id FROM articles WHERE id = :id"), {"id": article_id}).first() is None:
            return False
        if hidden:
            if connection.execute(select(hidden_table.c.article_id).where(hidden_table.c.article_id == article_id)).first() is None:
                connection.execute(hidden_table.insert().values(article_id=article_id))
        else:
            connection.execute(hidden_table.delete().where(hidden_table.c.article_id == article_id))
    return True
