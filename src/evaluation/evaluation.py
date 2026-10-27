from datetime import datetime

from src.embedding.hybrid_search import search_hybrid

test_cases = [
    {
        "topic": "UAV",
        "relevant": [
            "Tướng Ukraine: Nga đã phát triển UAV chuyên phá lưới điện",
            "Ấn Độ chi hơn 200 triệu USD để thuê hai UAV Mỹ",
            "Ukraine có thể đã dùng UAV Anh để tập kích lãnh thổ Nga"
        ]
    },
    {
        "topic": "Ukraine",
        "relevant": [
            "Ông Putin: 'Ukraine đã mở hộp Pandora'",
            "Ukraine có thể đã dùng UAV Anh để tập kích lãnh thổ Nga",
            "Ukraine phóng hơn 600 UAV nhằm vào Moskva, gây cháy nhà kho Wildberries"
        ]
    },
    {
        "topic": "Xuân Son",
        "relevant": [
            "CĐV trên phố đi bộ Nguyễn Huệ vỡ òa với cú đúp của Xuân Son",
            "CĐV ở phố đi bộ Nguyễn Huệ reo hò khi Việt Nam thắng Malaysia 2-0"
        ]
    },
    {
        "topic": "Ngô Thanh Vân",
        "relevant": [
            "Ngô Thanh Vân bế con catwalk"
        ]
    },
    {
        "topic": "Bitcoin",
        "relevant": [
            "Vì sao Bitcoin kém hấp dẫn hơn trước?"
        ]
    }
]


start_date = datetime.strptime(
    "01/08/2026",
    "%d/%m/%Y"
).date()


end_date = datetime.strptime(
    "23/08/2026",
    "%d/%m/%Y"
).date()


hit_rate_at_3 = 0
hit_rate_at_5 = 0


print("=" * 60)
print("HYBRID RECOMMENDATION EVALUATION")
print("=" * 60)


for test in test_cases:

    topic = test["topic"]
    relevant = test["relevant"]

    results = search_hybrid(
        topic,
        start_date,
        end_date,
        top_k=10
    )

    top3 = results[:3]
    top5 = results[:5]

    top3_titles = [
        result["title"]
        for result in top3
    ]

    top5_titles = [
        result["title"]
        for result in top5
    ]

    pass_top3 = any(
        title in relevant
        for title in top3_titles
    )

    pass_top5 = any(
        title in relevant
        for title in top5_titles
    )

    if pass_top3:
        hit_rate_at_3 += 1

    if pass_top5:
        hit_rate_at_5 += 1

    print("\n" + "=" * 60)
    print(f"TOPIC: {topic}")
    print("=" * 60)

    print("\nTop 5:")

    for rank, result in enumerate(
        top5,
        start=1
    ):
        print(
            f"{rank}. "
            f"{result['title']} "
            f"-> {result['hybrid_score']:.4f}"
        )

    print(
        f"\nHitRate@3: "
        f"{'PASS' if pass_top3 else 'FAIL'}"
    )

    print(
        f"HitRate@5: "
        f"{'PASS' if pass_top5 else 'FAIL'}"
    )


total_tests = len(test_cases)

hit_rate_at_3_score = hit_rate_at_3 / total_tests
hit_rate_at_5_score = hit_rate_at_5 / total_tests


print("\n" + "=" * 60)
print("FINAL RESULT")
print("=" * 60)

print(
    f"HitRate@3 = {hit_rate_at_3}/{total_tests} "
    f"= {hit_rate_at_3_score * 100:.2f}%"
)

print(
    f"HitRate@5 = {hit_rate_at_5}/{total_tests} "
    f"= {hit_rate_at_5_score * 100:.2f}%"
)