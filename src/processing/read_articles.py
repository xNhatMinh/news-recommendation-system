import json

with open(
    r"C:\news-recommendation-system\data\articles.json",
    "r",
    encoding="utf-8"
) as f:
    articles = json.load(f)

print("Number of articles:", len(articles))

article = articles[0]

title = article["title"]
description = article["description"]
content = article["content"]

text = title + "\n" + description + "\n" + content

print("Title:", title)
print("Description:", description)
print("Content length:", len(content))
print("Text length:", len(text))