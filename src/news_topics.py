"""Các chủ đề chính dùng cho trang chủ và crawler."""

from urllib.parse import urlparse


CRAWL_CATEGORIES = {
    "Thời sự": "https://vnexpress.net/thoi-su",
    "Thế giới": "https://vnexpress.net/the-gioi",
    "Kinh doanh": "https://vnexpress.net/kinh-doanh",
    "Khoa học": "https://vnexpress.net/khoa-hoc-cong-nghe",
    "Thể thao": "https://vnexpress.net/the-thao",
    "Giải trí": "https://vnexpress.net/giai-tri",
    "Sức khỏe": "https://vnexpress.net/suc-khoe",
    "Công nghệ": "https://vnexpress.net/khoa-hoc-cong-nghe/ai",
    "Giáo dục": "https://vnexpress.net/giao-duc",
    "Pháp luật": "https://vnexpress.net/phap-luat",
    "Du lịch": "https://vnexpress.net/du-lich",
    "Đời sống": "https://vnexpress.net/doi-song",
    "Xe": "https://vnexpress.net/oto-xe-may",
    "Bất động sản": "https://vnexpress.net/bat-dong-san",
}
MAIN_TOPICS = list(CRAWL_CATEGORIES)

# Báo gộp Khoa học và Công nghệ; các mục sau được tách vào Công nghệ.
TECHNOLOGY_SECTIONS = {
    "ai", "ai4vn-2026", "thiet-bi", "chuyen-doi-so", "doi-moi-sang-tao",
    "tech-awards", "nhip-song-so", "san-pham", "dien-tu-gia-dung",
}


def get_main_category(soup):
    """Đọc đường dẫn breadcrumb, không đoán chủ đề từ tiêu đề bài."""
    links = soup.select("ul.breadcrumb a[href]")
    roots = {urlparse(url).path.strip("/"): topic
             for topic, url in CRAWL_CATEGORIES.items()
             if topic != "Công nghệ"}
    roots.update({"khoa-hoc": "Khoa học", "so-hoa": "Công nghệ",
                  "cong-nghe": "Công nghệ", "gia-dinh": "Đời sống"})

    for link in reversed(links):
        parts = urlparse(link["href"]).path.strip("/").split("/")
        if parts[0] == "khoa-hoc-cong-nghe" and any(
            part in TECHNOLOGY_SECTIONS for part in parts[1:]
        ):
            return "Công nghệ"
        if parts[0] in roots:
            return roots[parts[0]]

    # Hỗ trợ trang chỉ có tên chuyên mục, thiếu đường dẫn chuẩn.
    for link in links:
        label = link.get_text(" ", strip=True)
        if label in MAIN_TOPICS:
            return label
        if label == "Khoa học công nghệ":
            return "Khoa học"
    return None
