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


test_cases = [
    {
        "name": "Vòm cầu",
        "target": 6,
        "relevant": [9]
    },
    {
        "name": "FIFA ASEAN Cup",
        "target": 45,
        "relevant": [52]
    },
    {
        "name": "Miss World",
        "target": 65,
        "relevant": [71, 60]
    },
    {
        "name": "Ronaldo",
        "target": 46,
        "relevant": [56]
    },
    {
        "name": "Máy bay",
        "target": 0,
        "relevant": [24, 40, 28]
    }
]


def get_similar_articles(target_index):
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
            "score": score
        })

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results


recall_at_3 = 0
recall_at_5 = 0

print("=" * 60)
print("RECOMMENDATION EVALUATION")
print("=" * 60)


for test in test_cases:

    name = test["name"]
    target = test["target"]
    relevant = test["relevant"]

    results = get_similar_articles(target)

    top3 = results[:3]
    top5 = results[:5]

    top3_indexes = [
        result["index"]
        for result in top3
    ]

    top5_indexes = [
        result["index"]
        for result in top5
    ]

    pass_top3 = any(
        index in relevant
        for index in top3_indexes
    )

    pass_top5 = any(
        index in relevant
        for index in top5_indexes
    )

    if pass_top3:
        recall_at_3 += 1

    if pass_top5:
        recall_at_5 += 1

    print(f"\nTest: {name}")
    print(
        f"Article: {embeddings[target]['title']}"
    )

    print("\nTop 5:")

    for rank, result in enumerate(
        top5,
        start=1
    ):
        print(
            f"{rank}. {result['title']} "
            f"-> {result['score']:.4f}"
        )

    print(
        f"\nRecall@3: "
        f"{'PASS' if pass_top3 else 'FAIL'}"
    )

    print(
        f"Recall@5: "
        f"{'PASS' if pass_top5 else 'FAIL'}"
    )


total_tests = len(test_cases)

recall_at_3_score = recall_at_3 / total_tests
recall_at_5_score = recall_at_5 / total_tests

print("\n" + "=" * 60)
print("FINAL RESULT")
print("=" * 60)

print(
    f"Recall@3 = {recall_at_3}/{total_tests} "
    f"= {recall_at_3_score * 100:.2f}%"
)

print(
    f"Recall@5 = {recall_at_5}/{total_tests} "
    f"= {recall_at_5_score * 100:.2f}%"
)