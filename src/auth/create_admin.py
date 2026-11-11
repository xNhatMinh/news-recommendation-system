"""Create the single admin account: username/password, no email required."""
import argparse
import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key
from src.api.security import hash_admin_password


def main():
    parser = argparse.ArgumentParser(description="Tạo tài khoản quản trị Newsora")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--credentials-file", required=True, help="Tệp riêng để nhận thông tin đăng nhập")
    args = parser.parse_args()
    if not args.username.isascii() or not args.username.replace("_", "").replace("-", "").isalnum() or not 3 <= len(args.username) <= 50:
        parser.error("Username cần 3-50 ký tự chữ, số, dấu gạch dưới hoặc gạch ngang")
    env_file = Path(__file__).resolve().parents[2] / ".env"
    values = dotenv_values(env_file)
    if values.get("ADMIN_PASSWORD_HASH"):
        parser.error("Tài khoản admin đã tồn tại; không ghi đè thông tin hiện có")
    password = secrets.token_urlsafe(18)
    target = Path(args.credentials_file)
    with target.open("x", encoding="utf-8") as output:
        output.write(f"Trang đăng nhập: http://127.0.0.1:8000/admin\nUsername: {args.username}\nPassword: {password}\n")
    set_key(str(env_file), "ADMIN_USERNAME", args.username)
    set_key(str(env_file), "ADMIN_PASSWORD_HASH", hash_admin_password(password))
    print("Đã tạo admin. Thông tin đăng nhập được lưu trong tệp riêng; hãy khởi động lại backend.")


if __name__ == "__main__":
    main()
