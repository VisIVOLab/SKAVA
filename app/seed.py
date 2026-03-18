from app.db import SessionLocal
from app.services.seed import seed_data


if __name__ == "__main__":
    with SessionLocal() as db:
        seed_data(db)
        print("Seed completed")
