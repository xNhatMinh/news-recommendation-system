from datetime import datetime

from src.embedding.hybrid_search import search_hybrid

start_date = datetime.strptime(
    "01/08/2026",
    "%d/%m/%Y"
).date()

end_date = datetime.strptime(
    "23/08/2026",
    "%d/%m/%Y"
).date()


topics = [
    "UAV",
    "Ukraine",
    "Nga",
    "Xuân Son",
    "Ngô Thanh Vân",
    "Tân Sơn Nhất",
    "Apple",
    "Bitcoin",
    "NASA"
]


for topic in topics:

    print("\n" + "=" * 70)
    print(f"TOPIC: {topic}")
    print("=" * 70)

    results = search_hybrid(
        topic,
        start_date,
        end_date,
        top_k=10
    )

    for i, result in enumerate(results, start=1):

        print(
            f"{i}. "
            f"{result['score']:.4f} - "
            f"{result['title']}"
        )