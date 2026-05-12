"""Verification ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .person import Person


class Verification(Base):
    """Represents a single signature verification event."""

    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode: Mapped[str] = mapped_column(String, nullable=False)
    reference_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    submitted_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    is_match: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    observations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    flagged_for_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    person: Mapped["Person | None"] = relationship("Person", back_populates="verifications")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "mode": self.mode,
            "reference_image_path": self.reference_image_path,
            "submitted_image_path": self.submitted_image_path,
            "verdict": self.verdict,
            "is_match": self.is_match,
            "confidence": self.confidence,
            "reason": self.reason,
            "observations_json": self.observations_json,
            "raw_response_json": self.raw_response_json,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "flagged_for_review": self.flagged_for_review,
            "exported": self.exported,
            "response_hash": self.response_hash,
        }
