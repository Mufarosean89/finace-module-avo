from utils.base_repository import BaseRepository
from .models import User


class UserRepository(BaseRepository[User]):
    model = User
