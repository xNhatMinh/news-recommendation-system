import json
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

with open(
    DATA_DIR / "embeddings.json",
    "r",
    encoding="utf-8"
) as f:
    embeddings = json.load(f)


target_index = 0
target_vector = embeddings[target_index]["vector"]

results = []

for i in range(len(embeddings)):

    if i == target_index:
        continue

    vector = embeddings[i]["vector"]

    score = cosine_similarity(
        [target_vector],
        [vector]
    )[0][0]

    results.append({
        "index": i,
        "title": embeddings[i]["title"],
        "url": embeddings[i]["url"],
        "score": score
    })


results.sort(
    key=lambda x: x["score"],
    reverse=True
)


print("Article đang xem:")
print(embeddings[target_index]["title"])

print("\nTop 5 bài tương tự:")

for i, result in enumerate(results[:5], start=1):

    print(
        f"{i}. {result['title']} "
        f"-> {result['score']:.4f}"
    )