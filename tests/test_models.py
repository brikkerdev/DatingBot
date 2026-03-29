"""Tests for model imports and basic structure."""

from src.db.models import Base, Like, Match, Message, Pass, Profile, ProfilePhoto, User, UserRating


def test_all_models_have_tablename():
    models = [User, Profile, ProfilePhoto, Like, Pass, Match, Message, UserRating]
    for model in models:
        assert hasattr(model, "__tablename__"), f"{model.__name__} missing __tablename__"


def test_user_tablename():
    assert User.__tablename__ == "users"


def test_profile_tablename():
    assert Profile.__tablename__ == "profiles"


def test_match_tablename():
    assert Match.__tablename__ == "matches"


def test_message_tablename():
    assert Message.__tablename__ == "messages"


def test_user_rating_tablename():
    assert UserRating.__tablename__ == "user_ratings"
