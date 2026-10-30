from pathlib import Path

import firebase_admin
from firebase_admin import credentials

BASE_DIR = Path(__file__).resolve().parents[2]

credential = credentials.Certificate(str(BASE_DIR / "firebase-service-account.json"))

firebase_app = firebase_admin.initialize_app(credential)
