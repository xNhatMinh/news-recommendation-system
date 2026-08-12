import json
from sentence_transformers import SentenceTransformer

with open(
    r"C:\news-recommendation-system\data\articles.json",
    "r",
    encoding="utf-8"
) as f:
    articles = json.load(f)


model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


texts = []

for article in articles:

    text = (
        article["title"]
        + "\n"
        + article["description"]
        + "\n"
        + article["content"]
    )

    texts.append(text)


vectors = model.encode(texts)


print("Number of articles:", len(articles))
print("Number of vectors:", len(vectors))
print("Vector length:", len(vectors[0]))

# Lưu embeddings
embedding_data = []

for i in range(len(articles)):

    embedding_data.append({
        "url": articles[i]["url"],
        "title": articles[i]["title"],
        "vector": vectors[i].tolist()
    })


with open(
    r"C:\news-recommendation-system\data\embeddings.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        embedding_data,
        f,
        ensure_ascii=False,
        indent=2
    )


print("Saved embeddings to data/embeddings.json")