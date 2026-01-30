from app.repositories.base import IFavoriteRepository
from app.repositories.memory import MockFavoriteRepository

__all__ = ["IFavoriteRepository", "MockFavoriteRepository"]
