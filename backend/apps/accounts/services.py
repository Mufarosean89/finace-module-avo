"""
Account service layer — user registration and profile management.
"""
from .repositories import UserRepository


class AccountService:
    """High-level account operations."""

    def __init__(self):
        self.user_repo = UserRepository()

    def register(self, email: str, password: str, name: str = ''):
        """Register a new user account."""
        return self.user_repo.model.objects.create_user(
            email=email,
            password=password,
            name=name,
        )

    def get_profile(self, user_id):
        """Get user profile."""
        return self.user_repo.get_by_id(user_id)
