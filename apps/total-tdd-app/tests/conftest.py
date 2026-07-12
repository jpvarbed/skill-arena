from datetime import date

import pytest

from shelfd import Shelfd


@pytest.fixture
def app():
    return Shelfd()


@pytest.fixture
def seeded(app):
    fiction = app.add_book("The Left Hand of Darkness", "Ursula K. Le Guin", year=1969, genres=["fiction", "sf"], copies=2)
    history = app.add_book("The Making of the Atomic Bomb", "Richard Rhodes", year=1986, genres=["history"], copies=1)
    poetry = app.add_book("Devotions", "Mary Oliver", year=2017, genres=["poetry"], copies=1)
    ada = app.register_member("Ada Lovelace", "ada@example.com", max_loans=3)
    grace = app.register_member("Grace Hopper", "grace@example.com", max_loans=2)
    linus = app.register_member("Linus Torvalds", "linus@example.com", max_loans=1)
    return {
        "app": app,
        "fiction": fiction,
        "history": history,
        "poetry": poetry,
        "ada": ada,
        "grace": grace,
        "linus": linus,
        "today": date(2026, 1, 10),
    }
