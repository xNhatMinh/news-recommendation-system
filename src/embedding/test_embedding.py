from sentence_transformers import SentenceTransformer

model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

text = "Samsung ra mắt điện thoại mới tích hợp AI"

vector = model.encode(text)

print(vector)
print("Vector length:", len(vector))