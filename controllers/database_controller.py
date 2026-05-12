"""Database controller for person and verification persistence operations."""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from database.db_manager import SessionLocal
from models.person import Person
from models.verification import Verification
from utils.logger import get_logger
from utils.validators import validate_confidence, validate_name

logger = get_logger("database_controller")


class DatabaseController:
    """Encapsulates database CRUD and analytics queries used by the UI."""

    VALID_VERDICTS = {"MATCH", "MISMATCH", "INCONCLUSIVE"}

    def add_person(
        self,
        full_name: str,
        signature_image_path: str,
        thumbnail_blob: bytes | None = None,
        notes: str | None = None,
    ) -> Person:
        valid, message = validate_name(full_name)
        if not valid:
            raise ValueError(message)

        try:
            with SessionLocal() as session:
                person = Person(
                    full_name=full_name.strip(),
                    signature_image_path=signature_image_path,
                    thumbnail_blob=thumbnail_blob,
                    notes=notes,
                )
                session.add(person)
                session.commit()
                session.refresh(person)
                logger.info("Person added: %s (id=%s)", person.full_name, person.id)
                return person
        except Exception as exc:
            logger.exception("Failed to add person")
            raise RuntimeError(f"Failed to add person: {exc}") from exc

    def get_person_by_id(self, person_id: int) -> Person | None:
        try:
            with SessionLocal() as session:
                return session.get(Person, person_id)
        except Exception:
            logger.exception("Failed to fetch person by id=%s", person_id)
            return None

    def get_all_persons(self, search_query: str = "") -> list[Person]:
        try:
            with SessionLocal() as session:
                stmt = select(Person)
                query = (search_query or "").strip()
                if query:
                    stmt = stmt.where(Person.full_name.ilike(f"%{query}%"))
                stmt = stmt.order_by(Person.created_at.desc())
                return list(session.scalars(stmt).all())
        except Exception:
            logger.exception("Failed to fetch persons list")
            return []

    def update_person(
        self,
        person_id: int,
        full_name: str | None = None,
        signature_image_path: str | None = None,
        thumbnail_blob: bytes | None = None,
        notes: str | None = None,
    ) -> Person | None:
        try:
            with SessionLocal() as session:
                person = session.get(Person, person_id)
                if person is None:
                    return None

                if full_name is not None:
                    valid, message = validate_name(full_name)
                    if not valid:
                        raise ValueError(message)
                    person.full_name = full_name.strip()

                if signature_image_path is not None:
                    person.signature_image_path = signature_image_path

                if thumbnail_blob is not None:
                    person.thumbnail_blob = thumbnail_blob

                if notes is not None:
                    person.notes = notes

                person.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(person)
                logger.info("Person updated: id=%s", person_id)
                return person
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update person id=%s", person_id)
            return None

    def delete_person(self, person_id: int) -> bool:
        try:
            with SessionLocal() as session:
                person = session.get(Person, person_id)
                if person is None:
                    return False
                name = person.full_name
                session.delete(person)
                session.commit()
                logger.info("Person deleted: %s (id=%s)", name, person_id)
                return True
        except Exception:
            logger.exception("Failed to delete person id=%s", person_id)
            return False

    def get_person_count(self) -> int:
        try:
            with SessionLocal() as session:
                return int(session.scalar(select(func.count()).select_from(Person)) or 0)
        except Exception:
            logger.exception("Failed to count persons")
            return 0

    def search_persons(self, query: str) -> list[Person]:
        return self.get_all_persons(search_query=query)

    def add_verification(
        self,
        person_id: int | None,
        mode: str,
        reference_image_path: str,
        submitted_image_path: str,
        verdict: str,
        confidence: float,
        reason: str,
        observations_json: str,
        raw_response_json: str,
    ) -> Verification:
        normalized_verdict = (verdict or "").strip().upper()
        if normalized_verdict not in self.VALID_VERDICTS:
            raise ValueError("Verdict must be MATCH, MISMATCH, or INCONCLUSIVE")

        confidence_ok, confidence_message = validate_confidence(confidence)
        if not confidence_ok:
            raise ValueError(confidence_message)

        try:
            with SessionLocal() as session:
                response_hash = hashlib.sha256(raw_response_json.encode("utf-8")).hexdigest()

                verification = Verification(
                    person_id=person_id,
                    mode=mode,
                    reference_image_path=reference_image_path,
                    submitted_image_path=submitted_image_path,
                    verdict=normalized_verdict,
                    is_match=1 if normalized_verdict == "MATCH" else 0,
                    confidence=float(confidence),
                    reason=reason,
                    observations_json=observations_json,
                    raw_response_json=raw_response_json,
                    response_hash=response_hash,
                )
                session.add(verification)
                session.commit()
                session.refresh(verification)
                logger.info("Verification added: id=%s verdict=%s", verification.id, normalized_verdict)
                return verification
        except Exception as exc:
            logger.exception("Failed to add verification")
            raise RuntimeError(f"Failed to add verification: {exc}") from exc

    def get_all_verifications(
        self,
        limit: int = 100,
        offset: int = 0,
        verdict_filter: str | None = None,
        search_name: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[Verification]:
        try:
            with SessionLocal() as session:
                stmt = (
                    select(Verification)
                    .outerjoin(Person, Verification.person_id == Person.id)
                    .options(joinedload(Verification.person))
                    .order_by(Verification.verified_at.desc())
                )

                if verdict_filter:
                    stmt = stmt.where(Verification.verdict == verdict_filter)

                if search_name:
                    stmt = stmt.where(Person.full_name.ilike(f"%{search_name.strip()}%"))

                if date_from is not None:
                    stmt = stmt.where(Verification.verified_at >= date_from)

                if date_to is not None:
                    stmt = stmt.where(Verification.verified_at <= date_to)

                stmt = stmt.offset(max(0, offset)).limit(max(1, limit))
                return list(session.scalars(stmt).all())
        except Exception:
            logger.exception("Failed to fetch verifications")
            return []

    def get_verification_by_id(self, verification_id: int) -> Verification | None:
        try:
            with SessionLocal() as session:
                stmt = (
                    select(Verification)
                    .where(Verification.id == verification_id)
                    .options(joinedload(Verification.person))
                )
                return session.scalar(stmt)
        except Exception:
            logger.exception("Failed to fetch verification by id=%s", verification_id)
            return None

    def get_verifications_today_count(self) -> int:
        try:
            with SessionLocal() as session:
                today_midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                stmt = select(func.count()).select_from(Verification).where(Verification.verified_at >= today_midnight)
                return int(session.scalar(stmt) or 0)
        except Exception:
            logger.exception("Failed to count today's verifications")
            return 0

    def get_average_confidence(self) -> float:
        try:
            with SessionLocal() as session:
                value = session.scalar(select(func.avg(Verification.confidence)))
                return float(value) if value is not None else 0.0
        except Exception:
            logger.exception("Failed to compute average confidence")
            return 0.0

    def get_last_verdict(self) -> str | None:
        try:
            with SessionLocal() as session:
                stmt = select(Verification.verdict).order_by(Verification.verified_at.desc()).limit(1)
                return session.scalar(stmt)
        except Exception:
            logger.exception("Failed to fetch last verdict")
            return None

    def get_recent_verifications(self, limit: int = 10) -> list[Verification]:
        try:
            with SessionLocal() as session:
                stmt = (
                    select(Verification)
                    .outerjoin(Person, Verification.person_id == Person.id)
                    .options(joinedload(Verification.person))
                    .order_by(Verification.verified_at.desc())
                    .limit(max(1, limit))
                )
                return list(session.scalars(stmt).all())
        except Exception:
            logger.exception("Failed to fetch recent verifications")
            return []

    def flag_verification(self, verification_id: int, flagged: bool = True) -> bool:
        try:
            with SessionLocal() as session:
                verification = session.get(Verification, verification_id)
                if verification is None:
                    return False
                verification.flagged_for_review = 1 if flagged else 0
                session.commit()
                return True
        except Exception:
            logger.exception("Failed to flag verification id=%s", verification_id)
            return False

    def mark_exported(self, verification_id: int) -> bool:
        try:
            with SessionLocal() as session:
                verification = session.get(Verification, verification_id)
                if verification is None:
                    return False
                verification.exported = 1
                session.commit()
                return True
        except Exception:
            logger.exception("Failed to mark verification as exported id=%s", verification_id)
            return False

    def update_verification_result(
        self,
        verification_id: int,
        verdict: str,
        is_match: int,
        confidence: float,
        reason: str,
        observations_json: str,
        raw_response_json: str,
        response_hash: str,
    ) -> bool:
        try:
            with SessionLocal() as session:
                verification = session.get(Verification, verification_id)
                if verification is None:
                    logger.warning("update_verification_result: id %s not found", verification_id)
                    return False

                verification.verdict = verdict
                verification.is_match = is_match
                verification.confidence = confidence
                verification.reason = reason
                verification.observations_json = observations_json
                verification.raw_response_json = raw_response_json
                verification.response_hash = response_hash

                session.commit()
                logger.info(
                    "Verification %s updated: verdict=%s, confidence=%.3f",
                    verification_id,
                    verdict,
                    confidence,
                )
                return True
        except Exception as exc:
            logger.error("update_verification_result error: %s", exc, exc_info=True)
            return False

    def get_total_records(self) -> int:
        return self.get_person_count()


database_controller = DatabaseController()

