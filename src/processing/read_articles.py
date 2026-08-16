import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


with open(
    DATA_DIR / "articles.json",
    "r",
    encoding="utf-8"
) as f:
    articles = json.load(f)


print("Number of articles:", len(articles))

for i, article in enumerate(articles):

    print("\n" + "=" * 80)

    print(f"Article {i}")

    print("Title:", article["title"])

    print("Description:", article["description"])

    print("Content length:", len(article["content"]))