import os
import json
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from google import genai

from src.embedding.hybrid_search import search_hybrid

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

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
Bạn là một hệ thống AI tổng hợp tin tức.

Chủ đề:
{topic}

Khoảng thời gian:
{start_date.strftime("%d/%m/%Y")} - {end_date.strftime("%d/%m/%Y")}

Dưới đây là các bài báo đã được hệ thống
xác định là có liên quan đến chủ đề.

{news_text}

Hãy tổng hợp các bài báo trên thành một bản tin
ngắn gọn và dễ hiểu.

Yêu cầu:
1. Chỉ sử dụng thông tin xuất hiện trong các bài báo.
2. Không tự bịa thêm thông tin.
3. Nêu các diễn biến và thông tin chính.
4. Nếu nhiều bài đề cập cùng một sự kiện thì gộp lại.
5. Không cần liệt kê lại toàn bộ nội dung từng bài.
6. Cuối cùng liệt kê các nguồn bài báo được sử dụng.
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    return response.text


def save_summary(
    topic,
    start_date,
    end_date,
    articles,
    summary
):
    output_file = DATA_DIR / "summaries.json"

    if output_file.exists():
        with open(
            output_file,
            "r",
            encoding="utf-8"
        ) as f:
            summaries = json.load(f)
    else:
        summaries = []

    summaries.append({
        "topic": topic,
        "start_date": start_date.strftime("%d/%m/%Y"),
        "end_date": end_date.strftime("%d/%m/%Y"),
        "articles": [
            {
                "title": article["title"],
                "url": article["url"],
                "published_at": article["published_at"],
                "hybrid_score": article["hybrid_score"]
            }
            for article in articles
        ],
        "summary": summary
    })

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            summaries,
            f,
            ensure_ascii=False,
            indent=2
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