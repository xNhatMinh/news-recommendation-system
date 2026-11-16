"""Compatibility command: store Firebase UID directly in users."""
from src.db.admin_store import init_user_columns


def create_firebase_accounts_table():
    init_user_columns()


if __name__ == "__main__":
    create_firebase_accounts_table()
    print("users.firebase_uid is ready; no separate Firebase accounts table is needed.")
