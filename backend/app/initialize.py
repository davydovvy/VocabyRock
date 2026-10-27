from .db import SessionLocal
from .seed import seed


def main():
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    main()
