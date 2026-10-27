from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSettings, Pack, PackWord, User, Word


DEMO = {
    "Animals": (
        "Meet furry and feathered friends",
        "Animals",
        [
            ("cat", "кошка", "/kæt/"),
            ("dog", "собака", "/dɔːɡ/"),
            ("bird", "птица", "/bɜːrd/"),
            ("fish", "рыба", "/fɪʃ/"),
            ("horse", "лошадь", "/hɔːrs/"),
            ("rabbit", "кролик", "/ˈræbɪt/"),
            ("bear", "медведь", "/ber/"),
            ("fox", "лиса", "/fɑːks/"),
            ("duck", "утка", "/dʌk/"),
            ("cow", "корова", "/kaʊ/"),
        ],
    ),
    "Food": (
        "Tasty words to learn",
        "Food",
        [
            ("apple", "яблоко", "/ˈæpəl/"),
            ("banana", "банан", "/bəˈnænə/"),
            ("bread", "хлеб", "/bred/"),
            ("milk", "молоко", "/mɪlk/"),
            ("cheese", "сыр", "/tʃiːz/"),
            ("carrot", "морковь", "/ˈkærət/"),
            ("egg", "яйцо", "/eɡ/"),
            ("water", "вода", "/ˈwɔːtər/"),
            ("orange", "апельсин", "/ˈɔːrɪndʒ/"),
            ("rice", "рис", "/raɪs/"),
        ],
    ),
    "Everyday Objects": (
        "Things all around you",
        "Home",
        [
            ("book", "книга", "/bʊk/"),
            ("chair", "стул", "/tʃer/"),
            ("table", "стол", "/ˈteɪbəl/"),
            ("door", "дверь", "/dɔːr/"),
            ("window", "окно", "/ˈwɪndoʊ/"),
            ("lamp", "лампа", "/læmp/"),
            ("ball", "мяч", "/bɔːl/"),
            ("bag", "сумка", "/bæɡ/"),
            ("pencil", "карандаш", "/ˈpensəl/"),
            ("clock", "часы", "/klɑːk/"),
        ],
    ),
}


def seed(db: Session):
    first_install = not db.scalar(select(User.id).limit(1))
    if not db.get(AppSettings, 1):
        db.add(AppSettings(id=1))
    if first_install:
        db.add_all(
            [
                User(role="parent", name="Parent", avatar="owl"),
                User(role="child", name="Explorer One", avatar="fox"),
                User(role="child", name="Explorer Two", avatar="bear"),
            ]
        )
    if first_install:
        for name, (description, category, entries) in DEMO.items():
            pack = Pack(name=name, description=description, category=category)
            db.add(pack)
            db.flush()
            for index, (english, russian, ipa) in enumerate(entries):
                word = Word(english=english, translations=[russian], ipa=ipa)
                db.add(word)
                db.flush()
                db.add(PackWord(pack_id=pack.id, word_id=word.id, position=index))
    db.commit()
