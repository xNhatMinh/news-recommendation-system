from sqlalchemy import text
from src.db.db import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Kết nối MySQL thành công!")
        print(result.fetchone())

except Exception as e:
    print("Kết nối thất bại:")
    print(e)