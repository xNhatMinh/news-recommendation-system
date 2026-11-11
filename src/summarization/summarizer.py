import os

from dotenv import load_dotenv
from google import genai

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