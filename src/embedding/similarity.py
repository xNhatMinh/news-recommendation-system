import json
from sklearn.metrics.pairwise import cosine_similarity


# Đọc embeddings
with open(
    r"C:\news-recommendation-system\data\embeddings.json",
    "r",
    encoding="utf-8"
) as f:
    embeddings = json.load(f)


# Chọn bài đang xem
target_index = 0

target_vector = embeddings[target_index]["vector"]

results = []

# So sánh với tất cả bài
for i in range(len(embeddings)):

    # Không so sánh bài với chính nó
    if i == target_index:
        continue

    vector = embeddings[i]["vector"]

    score = cosine_similarity(
        [target_vector],
        [vector]
    )[0][0]

    results.append({
        "title": embeddings[i]["title"],
        "score": score
    })


# Sắp xếp similarity từ cao xuống thấp
results.sort(
    key=lambda x: x["score"],
    reverse=True
)


# In bài đang xem
print("Article đang xem:")
print(embeddings[target_index]["title"])

print("\nTop 3 bài tương tự:")

for i, result in enumerate(results[:3], start=1):

    print(
        f"{i}. {result['title']} "
        f"-> {result['score']:.4f}"
    )