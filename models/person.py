"""Person ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .verification import Verification


class Person(Base):
    """Represents a person and their reference signature."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    signature_image_path: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_seed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    verifications: Mapped[list["Verification"]] = relationship(
        "Verification",
        back_populates="person",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            "Person("
            f"id={self.id}, "
            f"full_name={self.full_name!r}, "
            f"signature_image_path={self.signature_image_path!r}, "
            f"is_seed={self.is_seed}"
            ")"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "signature_image_path": self.signature_image_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "notes": self.notes,
            "is_seed": self.is_seed,
        }
