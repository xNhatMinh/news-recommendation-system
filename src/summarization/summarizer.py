import os
from datetime import datetime

from sqlalchemy import text
from src.db.db import engine
from dotenv import load_dotenv
from google import genai

from src.embedding.hybrid_search import search_hybrid

load_dotenv()


api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "Không tìm thấy GEMINI_API_KEY trong file .env"
    )


client = genai.Client(
    api_key=api_key
)


def summarize_articles(
    topic,
    start_date,
    end_date,
    articles
):

    news_text = ""

    for i, article in enumerate(articles, start=1):

        news_text += f"""
BÀI BÁO {i}

Tiêu đề:
{article['title']}

Ngày đăng:
{article['published_at']}

Mô tả:
{article['description']}

Nội dung:
{article['content']}

"""

        prompt = f"""
Hãy tổng hợp tin về chủ đề: {topic}.

Khoảng thời gian:
{start_date.strftime("%d/%m/%Y")} - {end_date.strftime("%d/%m/%Y")}

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

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )

    return response.text

def save_summary(
    user_id,
    topic,
    start_date,
    end_date,
    articles,
    summary
):
    with engine.begin() as connection:

        insert_summary = text("""
            INSERT INTO summaries (
                user_id,
                topic,
                start_date,
                end_date,
                summary
            )
            VALUES (
                :user_id,
                :topic,
                :start_date,
                :end_date,
                :summary
            )
            ON DUPLICATE KEY UPDATE
                id = LAST_INSERT_ID(id),
                summary = :summary,
                created_at = CURRENT_TIMESTAMP
        """)

        result = connection.execute(
            insert_summary,
            {
                "user_id": user_id,
                "topic": topic,
                "start_date": start_date,
                "end_date": end_date,
                "summary": summary
            }
        )

        summary_id = result.lastrowid

        delete_articles = text("""
            DELETE FROM summary_articles
            WHERE summary_id = :summary_id
        """)

        connection.execute(
            delete_articles,
            {
                "summary_id": summary_id
            }
        )

        find_article = text("""
            SELECT id
            FROM articles
            WHERE url = :url
        """)

        insert_summary_article = text("""
            INSERT INTO summary_articles (
                summary_id,
                article_id,
                hybrid_score
            )
            VALUES (
                :summary_id,
                :article_id,
                :hybrid_score
            )
        """)

        for article in articles:

            article_row = connection.execute(
                find_article,
                {
                    "url": article["url"]
                }
            ).fetchone()

            if article_row is None:
                continue

            connection.execute(
                insert_summary_article,
                {
                    "summary_id": summary_id,
                    "article_id": article_row.id,
                    "hybrid_score": article["hybrid_score"]
                }
            )

    print(
        f"\nĐã lưu summary vào MySQL "
        f"(summary_id = {summary_id})"
    )
    
def main():

    print("=" * 60)
    print("NEWS SUMMARIZATION")
    print("=" * 60)

    topic = input("Chủ đề: ")

    start_date_text = input(
        "Từ ngày (dd/mm/yyyy): "
    )

    end_date_text = input(
        "Đến ngày (dd/mm/yyyy): "
    )

    start_date = datetime.strptime(
        start_date_text,
        "%d/%m/%Y"
    ).date()

    end_date = datetime.strptime(
        end_date_text,
        "%d/%m/%Y"
    ).date()

    if start_date > end_date:
        print(
            "Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc."
        )
        return

    print("\nĐang tìm các bài báo liên quan...")

    results = search_hybrid(
        topic,
        start_date,
        end_date,
        top_k=10
    )

    if not results:
        print(
            "Không tìm thấy bài báo phù hợp."
        )
        return

    print(
        f"Tìm thấy {len(results)} bài báo."
    )

    print(
        "\nĐang tổng hợp bằng Gemini..."
    )

    summary = summarize_articles(
        topic,
        start_date,
        end_date,
        results
    )

    save_summary(
        topic,
        start_date,
        end_date,
        results,
        summary
    )

    print("\n" + "=" * 60)
    print("TỔNG HỢP")
    print("=" * 60)

    print(summary)


if __name__ == "__main__":
    main()