"""Seed data generation service."""

from __future__ import annotations

import random
import re
import shutil
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import func, select

from config import SEED_SIGNATURES_DIR, SIGNATURES_STORAGE_DIR
from database.db_manager import SessionLocal
from models.person import Person
from models.seed_image import SeedImage
from utils.logger import get_logger

logger = get_logger(__name__)


def _bezier_point(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float], t: float) -> tuple[float, float]:
    one_minus_t = 1.0 - t
    x = (
        (one_minus_t**3) * p0[0]
        + 3 * (one_minus_t**2) * t * p1[0]
        + 3 * one_minus_t * (t**2) * p2[0]
        + (t**3) * p3[0]
    )
    y = (
        (one_minus_t**3) * p0[1]
        + 3 * (one_minus_t**2) * t * p1[1]
        + 3 * one_minus_t * (t**2) * p2[1]
        + (t**3) * p3[1]
    )
    return x, y


def _curve_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 72,
) -> list[tuple[float, float]]:
    return [_bezier_point(p0, p1, p2, p3, i / steps) for i in range(steps + 1)]


def generate_signature_image(person_name: str, output_path: str) -> None:
    """Generate a realistic synthetic signature PNG image."""
    try:
        randomizer = random.Random(f"{person_name}-{random.random()}")
        canvas = Image.new("RGB", (400, 120), "#FFFFFF")
        draw = ImageDraw.Draw(canvas)
        ink_color = randomizer.choice(["#1A1A1A", "#2C2C2C"])

        for _ in range(randomizer.randint(3, 5)):
            start_x = randomizer.randint(12, 56)
            end_x = randomizer.randint(330, 390)
            baseline_y = randomizer.randint(48, 74)

            p0 = (start_x, baseline_y + randomizer.randint(-10, 8))
            p1 = (start_x + randomizer.randint(40, 110), baseline_y + randomizer.randint(-26, 22))
            p2 = (end_x - randomizer.randint(90, 150), baseline_y + randomizer.randint(-22, 24))
            p3 = (end_x, baseline_y + randomizer.randint(-10, 10))

            points = _curve_points(p0, p1, p2, p3)
            for index in range(len(points) - 1):
                width = randomizer.randint(1, 3)
                draw.line((points[index], points[index + 1]), fill=ink_color, width=width)

        flourish_points = _curve_points(
            (randomizer.randint(24, 72), randomizer.randint(82, 94)),
            (randomizer.randint(120, 180), randomizer.randint(96, 110)),
            (randomizer.randint(220, 300), randomizer.randint(88, 106)),
            (randomizer.randint(332, 388), randomizer.randint(84, 98)),
            steps=60,
        )
        for index in range(len(flourish_points) - 1):
            draw.line(
                (flourish_points[index], flourish_points[index + 1]),
                fill=ink_color,
                width=randomizer.randint(1, 2),
            )

        if randomizer.random() < 0.5:
            if randomizer.random() < 0.5:
                x = randomizer.randint(210, 340)
                y = randomizer.randint(24, 44)
                radius = randomizer.randint(2, 4)
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=ink_color)
            else:
                loop_center_x = randomizer.randint(170, 260)
                loop_center_y = randomizer.randint(30, 48)
                loop_points = _curve_points(
                    (loop_center_x - 10, loop_center_y),
                    (loop_center_x, loop_center_y - 12),
                    (loop_center_x + 16, loop_center_y + 10),
                    (loop_center_x - 4, loop_center_y + 6),
                    steps=36,
                )
                for index in range(len(loop_points) - 1):
                    draw.line(
                        (loop_points[index], loop_points[index + 1]),
                        fill=ink_color,
                        width=randomizer.randint(1, 2),
                    )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, format="PNG")
    except Exception as exc:
        logger.exception("Failed to generate seed signature image")
        raise RuntimeError(f"Failed to generate signature image for {person_name}: {exc}") from exc


def _build_thumbnail_blob(image_path: Path) -> bytes:
    with Image.open(image_path).convert("RGB") as image:
        thumbnail = image.resize((100, 40), Image.Resampling.LANCZOS)
        stream = BytesIO()
        thumbnail.save(stream, format="JPEG", quality=85)
        return stream.getvalue()


def _slugify_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "signature"


def run_seed_if_empty() -> None:
    """Populate initial seed records if the persons table is empty."""
    names = [
        "Raman Sharma",
        "Bharat Navya",
        "Vit Jyoti",
        "Jabeena Kapoor",
        "Saniya Rao",
        "Preethi Gingh",
        "Nikhitha Myer",
        "Rakesh Valhotra",
        "Kalyani Nair",
        "Pratyusha Verma",
    ]

    seed_dir_writable = True
    try:
        SEED_SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        seed_dir_writable = False
        logger.warning(
            "Seed signatures directory is not writable, using runtime generated signatures only: %s",
            SEED_SIGNATURES_DIR,
        )

    SIGNATURES_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        try:
            person_count = session.scalar(select(func.count()).select_from(Person)) or 0
            if person_count > 0:
                logger.info("Seed data already present, skipping")
                return

            for index, name in enumerate(names, start=1):
                filename = f"{index:02d}_{_slugify_name(name)}.png"
                seed_path = SEED_SIGNATURES_DIR / filename
                storage_path = SIGNATURES_STORAGE_DIR / filename

                source_image_path = seed_path
                if seed_path.exists():
                    source_image_path = seed_path
                elif seed_dir_writable:
                    generate_signature_image(name, str(seed_path))
                    source_image_path = seed_path
                else:
                    generate_signature_image(name, str(storage_path))
                    source_image_path = storage_path

                if source_image_path != storage_path:
                    shutil.copy2(source_image_path, storage_path)

                person = Person(
                    full_name=name,
                    signature_image_path=filename,
                    thumbnail_blob=_build_thumbnail_blob(source_image_path),
                    is_seed=1,
                )
                seed_image = SeedImage(
                    person_name=name,
                    image_filename=filename,
                    loaded=1,
                )

                session.add(person)
                session.add(seed_image)

            session.commit()
            logger.info("Seed data populated: 10 records created")
        except Exception as exc:
            session.rollback()
            logger.exception("Failed to populate seed data")
            raise RuntimeError(f"Failed to populate seed data: {exc}") from exc
