"""Seed image ORM model."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SeedImage(Base):
    """Tracks generated seed images loaded into the database."""

    __tablename__ = "seed_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_name: Mapped[str] = mapped_column(String, nullable=False)
    image_filename: Mapped[str] = mapped_column(String, nullable=False)
    loaded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
