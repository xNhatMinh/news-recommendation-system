import os
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from sqlalchemy import text

from src.db.db import engine
from src.embedding.hybrid_search import search_hybrid

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("Không tìm thấy GEMINI_API_KEY trong file .env")

GEMINI_MODEL = "gemini-3.5-flash-lite"
client = genai.Client(api_key=api_key)


def summarize_articles(topic, start_date, end_date, articles):
    """Ghép các bài thành một prompt và gọi Gemini một lần."""
    if not articles:
        raise ValueError("Không có bài báo để tổng hợp")

    parts = []
    for index, article in enumerate(articles, start=1):
        parts.append(f"""
BÀI BÁO {index}
Tiêu đề: {article['title']}
Ngày đăng: {article['published_at']}
Mô tả: {article['description']}
Nội dung: {article['content']}
""")
    news_text = "\n".join(parts)

    prompt = f"""
Hãy tổng hợp tin về chủ đề: {topic}.
Khoảng thời gian: {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}

Các bài báo:
{news_text}

Yêu cầu:
1. Chỉ dùng thông tin trong các bài báo, không tự bổ sung.
2. Viết tối đa 200 từ, dùng câu ngắn, dễ hiểu.
3. Trình bày tối đa 5 ý chính, mỗi ý bắt đầu bằng dấu •.
4. Mỗi ý dài 1-2 câu. Giữa các ý có một dòng trống.
5. Các bài nói về cùng sự kiện thì gộp lại.
6. Không viết lời mở đầu, kết luận hoặc danh sách nguồn.
7. Chỉ trả văn bản thuần, không dùng Markdown,
   không dùng ký hiệu # hoặc dấu * để định dạng.
"""
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


def save_summary(user_id, topic, start_date, end_date, articles, summary):
    """Lưu bản tổng hợp và danh sách bài báo nguồn trong cùng giao dịch."""
    insert_summary = text("""
        INSERT INTO summaries (user_id, topic, start_date, end_date, summary)
        VALUES (:user_id, :topic, :start_date, :end_date, :summary)
        ON DUPLICATE KEY UPDATE
            id = LAST_INSERT_ID(id),
            summary = :summary,
            created_at = CURRENT_TIMESTAMP
    """)
    find_article = text("SELECT id FROM articles WHERE url = :url")
    insert_source = text("""
        INSERT INTO summary_articles (summary_id, article_id, hybrid_score)
        VALUES (:summary_id, :article_id, :hybrid_score)
    """)

    with engine.begin() as connection:
        result = connection.execute(
            insert_summary,
            {
                "user_id": user_id,
                "topic": topic,
                "start_date": start_date,
                "end_date": end_date,
                "summary": summary,
            },
        )
        summary_id = result.lastrowid
        connection.execute(
            text("DELETE FROM summary_articles WHERE summary_id = :summary_id"),
            {"summary_id": summary_id},
        )
        for article in articles:
            row = connection.execute(find_article, {"url": article["url"]}).first()
            if row is None:
                continue
            connection.execute(
                insert_source,
                {
                    "summary_id": summary_id,
                    "article_id": row.id,
                    "hybrid_score": article["hybrid_score"],
                },
            )
    print(f"Đã lưu bản tổng hợp vào MySQL (id = {summary_id}).")


def main():
    user_id = int(input("User ID: "))
    topic = input("Chủ đề: ").strip()
    start_date = datetime.strptime(input("Từ ngày (dd/mm/yyyy): "), "%d/%m/%Y").date()
    end_date = datetime.strptime(input("Đến ngày (dd/mm/yyyy): "), "%d/%m/%Y").date()
    if start_date > end_date:
        print("Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc.")
        return

    results = search_hybrid(topic, start_date, end_date, top_k=10)
    if not results:
        print("Không tìm thấy bài báo phù hợp.")
        return

    print(f"Đang tổng hợp từ {len(results)} bài báo...")
    summary = summarize_articles(topic, start_date, end_date, results)
    save_summary(user_id, topic, start_date, end_date, results, summary)
    print(summary)


if __name__ == "__main__":
    main()
