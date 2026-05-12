"""Google Gemini service for signature verification."""

from __future__ import annotations

import ast
import concurrent.futures
from datetime import datetime
import hashlib
import importlib
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from controllers.settings_controller import settings_controller
from services.image_utils import ImageUtils
from utils.logger import get_logger


class GeminiService:
    """Encapsulates Gemini API communication and response parsing."""

    VALID_RESULTS = {"MATCH", "MISMATCH", "INCONCLUSIVE"}
    REQUIRED_OBSERVATION_KEYS = (
        "shape_similarity",
        "stroke_similarity",
        "letter_pattern_similarity",
        "alignment_similarity",
        "pen_pressure_consistency",
        "pen_speed_rhythm_consistency",
        "line_quality_consistency",
        "zone_proportion_match",
        "habitual_features_match",
        "paraph_flourish_match",
        "underscore_match",
        "loop_size_and_shape_match",
        "pen_lift_position_consistency",
        "entry_stroke_match",
        "exit_stroke_match",
        "baseline_consistency",
        "slant_angle_consistency",
        "stroke_direction_consistency",
        "hesitation_marks_detected",
        "retouching_or_patching_detected",
        "forgery_type_suspected",
        "natural_variation_within_expected_range",
        "image_quality_signature_1",
        "image_quality_signature_2",
        "image_quality_impact_on_confidence",
        "additional_anomalies",
    )
    OBSERVATION_KEY_ALIASES = {
        "shape": "shape_similarity",
        "stroke": "stroke_similarity",
        "letter_pattern": "letter_pattern_similarity",
        "alignment": "alignment_similarity",
        "pen_pressure": "pen_pressure_consistency",
        "pressure_consistency": "pen_pressure_consistency",
        "pen_speed_rhythm": "pen_speed_rhythm_consistency",
        "speed_rhythm_consistency": "pen_speed_rhythm_consistency",
        "line_quality": "line_quality_consistency",
        "zone_proportion": "zone_proportion_match",
        "habitual_features": "habitual_features_match",
        "paraph_flourish": "paraph_flourish_match",
        "underscore": "underscore_match",
        "loop_size_shape": "loop_size_and_shape_match",
        "pen_lift_positions": "pen_lift_position_consistency",
        "entry_stroke": "entry_stroke_match",
        "exit_stroke": "exit_stroke_match",
        "baseline": "baseline_consistency",
        "slant_angle": "slant_angle_consistency",
        "stroke_direction": "stroke_direction_consistency",
        "hesitation_marks": "hesitation_marks_detected",
        "retouching": "retouching_or_patching_detected",
        "forgery_type": "forgery_type_suspected",
        "natural_variation": "natural_variation_within_expected_range",
        "image_quality_1": "image_quality_signature_1",
        "image_quality_2": "image_quality_signature_2",
        "image_quality_impact": "image_quality_impact_on_confidence",
        "anomalies": "additional_anomalies",
    }
    DEFAULT_OBSERVATION_VALUE = "Unable to assess — not provided in model response"

    def __init__(self) -> None:
        self.logger = get_logger("gemini_service")

    def _print_raw_response_to_terminal(self, raw_text: str, model_name: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        header = (
            "\n"
            "========== GEMINI RAW RESPONSE START =========="
            f"\nTimestamp: {timestamp}"
            f"\nModel: {model_name}"
            "\nStatus: Received from Gemini, not parsed yet"
            "\n"
        )
        footer = "\n=========== GEMINI RAW RESPONSE END ===========\n"

        try:
            print(header + raw_text + footer, flush=True)
        except Exception as exc:
            self.logger.warning("Unable to print Gemini raw response in terminal: %s", exc)

        self.logger.info("Gemini raw response emitted to terminal before parsing")

    def _extract_finish_reason(self, response: Any) -> str:
        try:
            candidates = getattr(response, "candidates", None)
            if not candidates:
                return ""
            reason = getattr(candidates[0], "finish_reason", None)
            if reason is None:
                return ""
            return str(reason).strip().upper()
        except Exception:
            return ""

    def _has_unclosed_json_braces(self, text: str) -> bool:
        depth = 0
        in_string = False
        quote_char = ""
        escape = False

        for char in str(text or ""):
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote_char:
                    in_string = False
                continue

            if char in {'"', "'"}:
                in_string = True
                quote_char = char
                continue

            if char == "{":
                depth += 1
            elif char == "}" and depth > 0:
                depth -= 1

        return depth > 0

    def _is_response_truncated(self, response: Any, raw_text: str) -> bool:
        finish_reason = self._extract_finish_reason(response)
        finish_reason_hints = {
            "MAX_TOKENS",
            "MAX_TOKEN",
            "LENGTH",
            "TOKEN_LIMIT",
            "FINISH_REASON_MAX_TOKENS",
        }

        if any(hint in finish_reason for hint in finish_reason_hints):
            return True

        if self._has_unclosed_json_braces(raw_text):
            return True

        return False

    def _append_with_overlap(self, base_text: str, next_text: str) -> str:
        base = str(base_text or "")
        nxt = str(next_text or "")
        if not nxt:
            return base
        if not base:
            return nxt

        max_overlap = min(len(base), len(nxt), 3000)
        for overlap in range(max_overlap, 0, -1):
            if base.endswith(nxt[:overlap]):
                return base + nxt[overlap:]
        return base + nxt

    def _detect_mime_type(self, image_path: str) -> str:
        guessed, _ = mimetypes.guess_type(str(image_path))
        normalized = str(guessed or "").strip().lower()

        if normalized == "image/jpg":
            return "image/jpeg"

        if normalized in {"image/png", "image/jpeg", "image/webp"}:
            return normalized

        return "image/png"

    def _read_image_bytes_with_mime(self, image_path: str) -> tuple[bytes, str]:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()

        if not image_bytes:
            raise RuntimeError(f"Image payload is empty: {image_path}")

        return image_bytes, self._detect_mime_type(image_path)

    def _build_input_manifest_prompt(
        self,
        mode: str | None,
        reference_name: str,
        submitted_name: str,
        reference_hash: str,
        submitted_hash: str,
    ) -> str:
        mode_text = str(mode or "UNKNOWN").strip().upper() or "UNKNOWN"
        return (
            "INPUT MANIFEST\n"
            f"Verification mode: {mode_text}\n"
            "Image 1 is the REFERENCE signature. Use it as the baseline identity.\n"
            f"Image 1 filename: {reference_name}\n"
            f"Image 1 SHA256: {reference_hash}\n"
            "Image 2 is the SUBMITTED or QUESTIONED signature. Validate it against image 1.\n"
            f"Image 2 filename: {submitted_name}\n"
            f"Image 2 SHA256: {submitted_hash}\n"
            "Important: Keep image order fixed. Do not swap image identities."
        )

    def _get_api_key(self) -> str:
        api_key = settings_controller.get_api_key().strip()
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Gemini API key is not configured. Please add your API key in Settings.")
        return api_key

    def _get_model(self) -> str:
        return str(settings_controller.get("gemini_model", "gemini-2.5-flash") or "gemini-2.5-flash")

    def _build_forensic_prompt(self, person_name: str | None = None) -> str:
        prompt = """
# SIGNATURE VERIFICATION SYSTEM — SYSTEM PROMPT

---

## ROLE & IDENTITY

You are a **Forensic Signature Verification Expert AI**, trained to perform deep, multi-layered biometric analysis of handwritten signatures. You operate with the precision and rigor of a certified forensic document examiner (FDE) working in a legal, banking, or government-grade context. You must never guess, fabricate, or hallucinate results. Every observation you make must be directly grounded in what is visually present in the two provided signature images. Your output has real-world consequences — treat every analysis as if it could be submitted as forensic evidence in a court of law.

---

## PRIMARY TASK

You will be given **two signature images**. Your task is to determine whether both signatures were written by the **same person** or by **two different people**. You must analyze both signatures using **every available forensic and visual strategy** listed below. You must **not skip any strategy** under any circumstances, regardless of how obvious the result may seem early in the analysis.

---

## WHAT YOU MUST NEVER DO (CRITICAL GUARDRAILS)

Before analysis begins, internalize these absolute rules:

- **NEVER guess or assume** a result before completing full analysis.
- **NEVER skip any analysis strategy** — even if you believe you already have a clear answer.
- **NEVER base your conclusion only on visual similarity at first glance**. First-glance similarity is a known forensic trap. Skilled forgers can replicate surface appearance but fail on micro-level attributes.
- **NEVER ignore one image** — both must be analyzed individually first, then compared.
- **NEVER fabricate observations** you cannot actually see in the images.
- **NEVER return a high confidence score without completing all layers of analysis**.
- **NEVER ignore image quality issues**. If an image is low resolution, blurred, partially cut off, or poorly lit, you must flag it in your reasoning and reduce confidence accordingly.
- **NEVER confuse natural variation with forgery**, and **NEVER confuse skilled forgery with genuine variation**. This is the hardest part of forensic analysis — reason carefully.
- **NEVER output MATCH or MISMATCH without also providing full reasoning** across every observation category.
- **NEVER assume that because two signatures look different on the surface, they are from different people** — natural variation in a single person's signing style can be significant.
- **NEVER assume that because two signatures look identical, they must be genuine** — traced or digitally duplicated forgeries can look visually identical but fail other tests.

---

## COMPLETE ANALYSIS STRATEGY (ALL STRATEGIES MANDATORY)

You must work through all of the following strategies in sequence. Do not skip any. Even if the images are of poor quality, you must attempt every strategy and note what you can and cannot assess.

---

### STRATEGY 1 — INDIVIDUAL BASELINE ANALYSIS (PRE-COMPARISON)

Before comparing the two signatures, analyze each one independently.

For each signature:
- Identify the **starting stroke** — where the pen first touches the paper, the entry angle, the curve or direction of the first mark.
- Identify the **ending stroke** — where the pen lifts, the terminal direction, and whether it trails off or ends abruptly.
- Map the **overall form** — is it cursive, printed, mixed, highly stylized, or abstract?
- Identify any **letters or letter fragments** that may be embedded in the signature.
- Note the **spatial envelope** — the bounding box of the signature, its width-to-height ratio, and how the strokes fill that space.
- Note the **baseline** — does the signature sit on a line, drift upward, downward, or undulate?
- Note the **slant/tilt** of the overall signature and of individual letter bodies.
- Identify any **signature elements** such as underscores, loops, dots, dashes, crossed letters (e.g., crossed T), paraph (flourish at the end), or encircling strokes.

---

### STRATEGY 2 — MORPHOLOGICAL (SHAPE) ANALYSIS

Compare the physical form and geometry of the signatures.

- **Overall shape**: Does the general outline/silhouette of both signatures match?
- **Loop size and shape**: Are enclosed loops (in letters like o, e, l, d, g, p, etc.) proportionally similar in both?
- **Arch height**: Do upstroke and downstroke arches reach similar heights relative to the body of the signature?
- **Connection patterns**: Are strokes connected in the same way? Cursive joins between letters tend to be highly habitual and consistent.
- **Open vs. closed forms**: Are letters that should be closed (like 'a', 'o') open in the same way in both signatures?
- **Letter spacing**: Is the relative spacing between elements consistent?
- **Proportional relationships**: Does the ratio of tall letters (ascenders) to short letters (middle zone) stay consistent?

---

### STRATEGY 3 — STROKE-LEVEL ANALYSIS

Analyze individual strokes — the atomic units of a signature.

- **Stroke direction**: In both signatures, do strokes flow in the same directions? (e.g., clockwise vs. counter-clockwise loops)
- **Stroke sequence / pen order**: Based on visible overlaps and crossings, does the implied pen order match between the two signatures?
- **Stroke curvature**: Are curved strokes consistently curved (or straight) at the same points?
- **Retrace patterns**: Does the pen double back along existing paths? If yes, does this occur in the same places in both signatures?
- **Tremor or fluency indicators**: Are strokes smooth and fluid, or do they show hesitation, tremor, patching, or touch-ups? (Patching and hesitation are strong forgery indicators.)
- **Pen lifts**: Are there implied pen lifts in the same locations? A genuine signer tends to lift the pen in habitual, consistent locations.
- **Entry and exit angles per stroke**: The angle at which each stroke begins and ends is habitual and hard to forge.
- **Hook formations**: Are hooks (small curved terminals) at the beginning or end of strokes present or absent in both?

---

### STRATEGY 4 — PEN PRESSURE ANALYSIS

Pen pressure is one of the most reliable forensic indicators because it is largely subconscious.

- **Overall pressure level**: Does the ink appear to be applied with heavy or light pressure in both images?
- **Pressure distribution**: Identify areas where ink appears darker or heavier — these correspond to higher pressure zones. Are these zones in the same positions in both signatures?
- **Shading patterns**: As a pen moves at varying speeds and angles, it shades differently. Are shading gradients consistent?
- **Thin-to-thick transitions**: In upstrokes vs. downstrokes, does the line weight change in the same way? (Especially relevant if the instrument is a fountain pen or flex nib.)
- **Pressure anomaly flags**: If one signature shows consistent pressure but another shows abrupt, uneven pressure changes mid-stroke, this is a forgery indicator — note it.
- **Note**: If the images are digital or scanned low-resolution, full pressure analysis may not be possible. Document this limitation.

---

### STRATEGY 5 — PEN SPEED AND RHYTHM ANALYSIS

Writing speed produces characteristic visual signatures in the ink trace.

- **Stroke fluency**: Fast strokes tend to be thinner, smoother, and more simplified. Slow strokes tend to be thicker, more careful-looking, with more defined outlines. Are both signatures written at a similar implied speed?
- **Simplified vs. elaborate strokes**: At high speed, writers simplify their strokes habitually. Does the simplification pattern match across both signatures?
- **Rhythm of the signature**: Is there an implied rhythm or cadence (e.g., fast opening, slow middle, fast flourish)? Does this rhythm match?
- **Ink pooling**: Ink pools slightly when the pen pauses. Are ink pools present in the same locations?
- **Blunt starts and stops**: Rapidly made strokes often begin and end with tapered, blunt, or knife-like tips. Are these tips consistent in shape and location?

---

### STRATEGY 6 — LINE QUALITY ANALYSIS

Line quality is the overall smoothness, confidence, and consistency of the drawn line.

- **Smoothness**: Are the lines continuously smooth or do they waver, correct, or patch?
- **Tremor or shakiness**: Any visible tremor must be noted. Is it present in both (possibly genuine aging or medical condition) or only one (possible forgery)?
- **Pen hesitation marks**: Small indentations or ink pools where the pen paused before continuing are hesitation marks — a sign of careful, copied writing rather than habitual, automatic signing.
- **Retouching**: Are any strokes visibly repaired or retouched? This is a major red flag for forgery.
- **Confident vs. uncertain stroke quality**: Genuine signatures are typically written with confidence (automaticity). Forged signatures often look careful and studied.

---

### STRATEGY 7 — PROPORTIONAL AND ZONAL ANALYSIS

Handwriting analysts use a three-zone system: upper zone (ascenders like b, d, h, k, l), middle zone (body of lowercase letters), and lower zone (descenders like g, j, p, q, y).

- **Zone proportions**: Do the ratios between upper, middle, and lower zones match across both signatures?
- **Dominant zone**: Every person has a dominant zone (where most of their signature energy is concentrated). Is the same zone dominant in both?
- **Absolute vs. relative sizing**: Signatures may be written at different sizes on different occasions (natural), but the internal proportional relationships should remain stable.
- **Horizontal span**: Does the horizontal distance the signature travels feel proportionally similar?
- **Vertical amplitude**: How high and how low does the signature go relative to its own middle zone?

---

### STRATEGY 8 — LETTER FORM AND CONSTRUCTION ANALYSIS

If any letterforms are identifiable in the signatures:

- **Letter construction method**: How is each letter built? (e.g., does the 'r' curve up or arch? Does the 's' curve left or right? Does the 'f' have a loop or not?)
- **Idiosyncratic letter forms**: Many signers develop unique constructions for specific letters (e.g., a specific way of making the capital letter of their name). Are these present in both?
- **Upper case vs. lower case letters**: Are the same letters capitalized in both signatures?
- **Abbreviated vs. complete letters**: Are the same letters abbreviated or fully written in both?
- **Connection style per letter pair**: The way specific consecutive letters connect is habitual. Do the same letter pairs connect in the same way?

---

### STRATEGY 9 — HABITUAL FEATURES AND PERSONAL CHARACTERISTICS ANALYSIS

Every signer has unique habitual features that appear consistently across genuine signatures. These are highly individual and very difficult to replicate.

- **Paraph (terminal flourish)**: Does a flourish exist at the end? Is its direction, curvature, and style consistent?
- **Underscoring**: Is there an underline? If yes, is it in the same position, length, angle, and style?
- **Dots and dashes**: Are any dots or crossing marks (like the dot of an 'i' or the cross of a 't') placed in consistent positions?
- **Initial hooks**: Some signers begin with an entry stroke before the first visible letter. Is this present or absent consistently?
- **Enclosing strokes**: Some signatures wrap around or loop back. Is this present in both?
- **Abbreviation habits**: Does the signer consistently abbreviate part of their name in the same way?
- **Embellishments**: Any decorative or idiosyncratic additions — are they present, absent, or different between the two?

---

### STRATEGY 10 — NATURAL VARIATION ASSESSMENT

This is a critical strategy to avoid false mismatches.

- A single person's signatures will naturally vary. The question is: does the variation observed fall within normal human variation for a genuine signer, or does it exceed it?
- **Normal variation includes**: slight size changes, minor baseline shifts, small proportional differences, occasional stroke simplifications or extensions.
- **Abnormal variation (potential forgery indicator) includes**: reversal of stroke direction, opposite slant direction, fundamentally different letter constructions, completely absent habitual features, significantly different pressure patterns, or the presence of hesitation marks in one but not the other.
- Explicitly state whether the differences observed are **within expected natural variation** or **outside expected natural variation**, and why.

---

### STRATEGY 11 — FORGERY PATTERN RECOGNITION

Specifically check for known forgery types:

- **Simulated forgery**: The forger has studied the target signature and attempts to draw it from memory or reference. Signs: hesitation marks, slow drawing speed indicators, incorrect pen lifts, imprecise loop sizes, patching.
- **Traced forgery**: A genuine signature is traced directly. Signs: unusually consistent outline shape (too perfect), complete absence of fluency variation, possible offset or double-line artifacts from imperfect tracing.
- **Freehand forgery**: The forger writes freely without tracing, aiming for similarity. Signs: overall shape may be close but micro-level features (pressure, speed, pen lifts) diverge.
- **Digital manipulation**: The image itself may be digitally altered. Signs: resolution inconsistencies around the signature boundary, copy-paste artifacts, pixel-level inconsistencies.
- **Auto-forgery (disguised signature)**: A person attempts to disguise their own signature. Signs: unnatural hesitation in an otherwise confident writer, unusual deliberateness.
- After checking each type, state which (if any) appears applicable.

---

### STRATEGY 12 — CONTEXTUAL AND IMAGE QUALITY ASSESSMENT

Before finalizing, assess the quality of the inputs themselves.

- **Image resolution**: Is the image high enough to see fine stroke details?
- **Contrast**: Is the ink clearly distinguishable from the paper?
- **Lighting uniformity**: Are there shadows, glare, or uneven lighting that obscure details?
- **Angle/perspective distortion**: Was the image taken at an angle, causing trapezoidal distortion?
- **Cropping**: Is the full signature visible, or are parts cut off?
- **Ink or paper condition**: Is the signature on a wrinkled, stamped, or dirty background?
- **Overlay or noise**: Are there any background elements, stamps, or watermarks interfering?
- For each issue found, state how it impacts your confidence and which strategies were affected.
- **Do not artificially inflate confidence** if image quality was poor. Reduce confidence proportionally.

---

### STRATEGY 13 — CROSS-SIGNATURE CONSISTENCY SCORING (INTERNAL SCORING)

Before generating the final JSON, internally score each of the following dimensions on a 0–10 scale and use these scores to compute your final confidence:

| Dimension | Score (0–10) |
|---|---|
| Overall shape similarity | ? |
| Stroke direction consistency | ? |
| Pen pressure consistency | ? |
| Pen speed/rhythm consistency | ? |
| Line quality consistency | ? |
| Habitual features match | ? |
| Zone proportions match | ? |
| Letter form match (if applicable) | ? |
| Natural variation assessment | ? |
| Absence of forgery indicators | ? |

Compute a weighted average (you may weight habitual features, stroke direction, and forgery absence more heavily, as these are most forensically reliable). This score maps directly to your `confidence` field in the output JSON.

---

## THINGS CLAUDE (AI) IS KNOWN TO GET WRONG — MANDATORY SELF-CHECK

Before finalizing your output, verify you have NOT committed any of the following common AI errors in document analysis:

1. **Over-relying on visual similarity**: You may perceive two signatures as similar just because they share a general shape. Deep analysis often reveals critical differences beneath surface appearance.
2. **Under-weighting micro-features**: Pressure, pen lift positions, stroke direction reversals, and line quality are often MORE diagnostically reliable than overall shape. Do not neglect these.
3. **Ignoring natural variation and calling it a mismatch**: Two genuine signatures from the same person can look quite different. Always assess variation within the context of expected human behavior.
4. **Treating absence of information as negative evidence**: If you cannot see pressure differences due to image quality, this is NOT evidence of pressure similarity — it is simply unknown. Flag it as such.
5. **Fabricating confidence**: Do not output `0.92` confidence when the images were low resolution and only 3 out of 13 strategies could be fully applied. Scale your confidence honestly.
6. **Anchoring on first impression**: You may initially perceive a match or mismatch. This must NOT anchor your conclusion. Complete all strategies before deciding.
7. **Ignoring forgery type differentiation**: Simply saying "this looks forged" is insufficient. Identify WHICH type of forgery pattern is suspected.
8. **Symmetry bias**: Do not rate two signatures as similar simply because both look "neat" or "chaotic." The structure of the neatness or chaos must match.
9. **Missing what is NOT there**: A habitual feature present in one but absent in the other is as important as a feature that IS present. Always check for absent elements.
10. **Conflating confident output with accurate output**: Your response must reflect genuine uncertainty when it exists. A real forensic examiner says "inconclusive" when evidence is insufficient.

---

## OUTPUT FORMAT (MANDATORY — RETURN EXACTLY THIS JSON STRUCTURE)

After completing all 13 strategies above, output your final result in the following JSON format. Do not return anything before or after the JSON block. Every field is mandatory. Do not omit, skip, or null any `observations` sub-field unless the image quality made it completely impossible to assess (in which case set the value to `"Unable to assess — [reason]"`).

```json
{
  "is_match": true,
  "result": "MATCH",
  "confidence": 0.92,
  "matched_person": "Person name if available from context, otherwise null",
  "reason": "A concise but specific explanation of why the signatures match or do not match, referencing the most decisive forensic indicators observed.",
  "observations": {
    "shape_similarity": "High / Medium / Low",
    "stroke_similarity": "High / Medium / Low",
    "letter_pattern_similarity": "High / Medium / Low",
    "alignment_similarity": "High / Medium / Low",
    "pen_pressure_consistency": "High / Medium / Low / Unable to assess — [reason]",
    "pen_speed_rhythm_consistency": "High / Medium / Low / Unable to assess — [reason]",
    "line_quality_consistency": "High / Medium / Low",
    "zone_proportion_match": "High / Medium / Low",
    "habitual_features_match": "High / Medium / Low",
    "paraph_flourish_match": "Present and matching / Present but different / Absent in one / Absent in both / Unable to assess",
    "underscore_match": "Present and matching / Present but different / Absent in one / Absent in both / Unable to assess",
    "loop_size_and_shape_match": "High / Medium / Low / Unable to assess",
    "pen_lift_position_consistency": "High / Medium / Low / Unable to assess",
    "entry_stroke_match": "High / Medium / Low",
    "exit_stroke_match": "High / Medium / Low",
    "baseline_consistency": "High / Medium / Low",
    "slant_angle_consistency": "High / Medium / Low",
    "stroke_direction_consistency": "High / Medium / Low",
    "hesitation_marks_detected": "Yes — in signature 1 / Yes — in signature 2 / Yes — in both / No",
    "retouching_or_patching_detected": "Yes — in signature 1 / Yes — in signature 2 / Yes — in both / No",
    "forgery_type_suspected": "None / Simulated / Traced / Freehand / Digital manipulation / Auto-forgery / Inconclusive",
    "natural_variation_within_expected_range": "Yes / No / Borderline",
    "image_quality_signature_1": "High / Medium / Low",
    "image_quality_signature_2": "High / Medium / Low",
    "image_quality_impact_on_confidence": "None / Minor / Moderate / Significant",
    "additional_anomalies": "Any other forensic observations not covered above, or 'None'"
  }
}
```

---

## RESULT VALUES (USE EXACTLY THESE STRINGS)

- `result`: Must be exactly one of: `"MATCH"`, `"MISMATCH"`, `"INCONCLUSIVE"`
- `is_match`: `true` for MATCH, `false` for MISMATCH or INCONCLUSIVE
- `confidence`: A float between `0.00` and `1.00`. Use `0.00–0.49` for MISMATCH, `0.50–0.65` for INCONCLUSIVE, `0.66–1.00` for MATCH
- If result is `INCONCLUSIVE`, set `is_match` to `false` and clearly explain why in `reason`

---

## STRATEGIES NOT EXPLICITLY LISTED ABOVE — MANDATORY COVERAGE

If you are aware of any additional forensic, biometric, or document examination technique that applies to signature verification and is not explicitly listed in Strategies 1–13 above, **you must apply it anyway**. This prompt does not claim to be exhaustive of the forensic science field. Examples of additional applicable techniques you must include if applicable:

- **Infrared or UV response observation** (if the image quality or source suggests this data is embedded)
- **Paper indentation analysis** (if a physical document scan reveals indented strokes from pressure)
- **Ink chemistry differences** (if the image reveals obvious tonal differences suggesting different ink types or instruments)
- **Instrument type identification** (ballpoint vs. gel vs. fountain pen — do both signatures appear made with the same instrument?)
- **Writing instrument angle**: The angle of the pen creates characteristic thickening on one side of strokes — are these consistent?
- **Relative size calibration**: If one image includes a reference object (e.g., a form background), use it to estimate absolute size and compare to the second signature's absolute size.

Do not skip anything in this category. The prompt explicitly requires full coverage.

---

*End of System Prompt*
""".strip()

        if person_name:
            prompt += (
                f"\n\nThe reference signature belongs to a person named '{person_name}'. "
                "Use this only as context, not as a basis for your analysis."
            )
        return prompt

    def _sanitize_observation_key(self, key: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")

    def _extract_json_objects(self, text: str) -> list[str]:
        objects: list[str] = []
        depth = 0
        start_idx = -1
        in_string = False
        quote_char = ""
        escape = False

        for idx, char in enumerate(text):
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote_char:
                    in_string = False
                continue

            if char in {'"', "'"}:
                in_string = True
                quote_char = char
                continue

            if char == "{":
                if depth == 0:
                    start_idx = idx
                depth += 1
            elif char == "}" and depth > 0:
                depth -= 1
                if depth == 0 and start_idx >= 0:
                    objects.append(text[start_idx : idx + 1])
                    start_idx = -1

        return objects

    def _iter_json_candidates(self, text: str) -> list[str]:
        raw = str(text or "").strip()
        if not raw:
            return []

        candidates: list[str] = [raw]

        if raw.lower().startswith("json"):
            candidates.append(raw[4:].strip())

        fence_pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
        for snippet in fence_pattern.findall(raw):
            cleaned_snippet = str(snippet or "").strip()
            if cleaned_snippet:
                candidates.append(cleaned_snippet)

        for snippet in self._extract_json_objects(raw):
            cleaned_snippet = snippet.strip()
            if cleaned_snippet:
                candidates.append(cleaned_snippet)

        unique_candidates: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        return unique_candidates

    def _relax_json_text(self, text: str) -> str:
        relaxed = str(text or "").strip().lstrip("\ufeff")
        relaxed = relaxed.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        relaxed = re.sub(r"^\s*json\s*", "", relaxed, count=1, flags=re.IGNORECASE)

        previous = None
        while previous != relaxed:
            previous = relaxed
            relaxed = re.sub(r",\s*([}\]])", r"\1", relaxed)

        return relaxed

    def _replace_json_literals_for_python(self, text: str) -> str:
        data = str(text or "")
        out: list[str] = []
        idx = 0
        in_string = False
        quote_char = ""
        escape = False

        def _is_boundary(pos: int) -> bool:
            return pos < 0 or pos >= len(data) or not (data[pos].isalnum() or data[pos] == "_")

        while idx < len(data):
            char = data[idx]

            if in_string:
                out.append(char)
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote_char:
                    in_string = False
                idx += 1
                continue

            if char in {'"', "'"}:
                in_string = True
                quote_char = char
                out.append(char)
                idx += 1
                continue

            if data.startswith("true", idx) and _is_boundary(idx - 1) and _is_boundary(idx + 4):
                out.append("True")
                idx += 4
                continue

            if data.startswith("false", idx) and _is_boundary(idx - 1) and _is_boundary(idx + 5):
                out.append("False")
                idx += 5
                continue

            if data.startswith("null", idx) and _is_boundary(idx - 1) and _is_boundary(idx + 4):
                out.append("None")
                idx += 4
                continue

            out.append(char)
            idx += 1

        return "".join(out)

    def _parse_json_candidate(self, candidate: str) -> dict[str, Any] | None:
        if not candidate:
            return None

        relaxed = self._relax_json_text(candidate)
        parse_attempts: list[str] = [relaxed]

        first_brace = relaxed.find("{")
        if first_brace > 0:
            parse_attempts.append(relaxed[first_brace:])

        for attempt in parse_attempts:
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    return parsed[0]
            except JSONDecodeError:
                pass

            try:
                python_literal = self._replace_json_literals_for_python(attempt)
                parsed_literal = ast.literal_eval(python_literal)
                if isinstance(parsed_literal, dict):
                    return parsed_literal
                if isinstance(parsed_literal, list) and parsed_literal and isinstance(parsed_literal[0], dict):
                    return parsed_literal[0]
            except (SyntaxError, ValueError):
                pass

        return None

    def _coerce_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return bool(int(value))
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "match", "matched"}:
                return True
            if normalized in {"false", "0", "no", "n", "mismatch", "inconclusive", "not_match"}:
                return False
        return None

    def _normalize_result_value(self, payload: dict[str, Any]) -> str:
        candidate = payload.get("result")
        if candidate is None:
            candidate = payload.get("verdict")

        if candidate is None:
            return "MATCH" if self._coerce_bool(payload.get("is_match")) else "INCONCLUSIVE"

        normalized = str(candidate).strip().upper()
        aliases = {
            "MATCHED": "MATCH",
            "SAME": "MATCH",
            "TRUE": "MATCH",
            "YES": "MATCH",
            "NOT MATCH": "MISMATCH",
            "NOT_MATCH": "MISMATCH",
            "DIFFERENT": "MISMATCH",
            "FALSE": "MISMATCH",
            "NO": "MISMATCH",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in self.VALID_RESULTS:
            return "INCONCLUSIVE"
        return normalized

    def _normalize_confidence_value(self, value: Any, result: str) -> float:
        defaults = {"MATCH": 0.66, "INCONCLUSIVE": 0.50, "MISMATCH": 0.35}

        try:
            if isinstance(value, str):
                cleaned = value.strip()
                is_percent = cleaned.endswith("%")
                numeric_value = float(cleaned.rstrip("%"))
                parsed = numeric_value / 100.0 if is_percent else numeric_value
            else:
                parsed = float(value)
        except (TypeError, ValueError):
            parsed = defaults.get(result, 0.50)

        if parsed > 1.0 and parsed <= 100.0:
            parsed = parsed / 100.0

        clamped = max(0.0, min(1.0, parsed))
        if result == "MISMATCH":
            clamped = min(clamped, 0.49)
        elif result == "INCONCLUSIVE":
            clamped = min(max(clamped, 0.50), 0.65)
        elif result == "MATCH":
            clamped = max(clamped, 0.66)

        if clamped != parsed:
            self.logger.warning(
                "Confidence %.4f adjusted to %.4f for result %s",
                parsed,
                clamped,
                result,
            )
        return clamped

    def _normalize_matched_person_value(self, value: Any, person_name: str | None, result: str) -> str | None:
        if value is None:
            return person_name if result == "MATCH" and person_name else None

        text_value = str(value).strip()
        if not text_value or text_value.lower() in {"null", "none", "n/a", "na", "unknown"}:
            return person_name if result == "MATCH" and person_name else None

        return text_value

    def _normalize_observations(self, observations_raw: Any) -> dict[str, str]:
        source: dict[str, Any] = {}

        if isinstance(observations_raw, dict):
            source = dict(observations_raw)
        elif isinstance(observations_raw, list):
            for item in observations_raw:
                if not isinstance(item, dict):
                    continue
                feature = item.get("feature") or item.get("name") or item.get("key")
                rating = item.get("rating") or item.get("value") or item.get("observation")
                if feature:
                    source[str(feature)] = rating

        canonical_key_map = {
            self._sanitize_observation_key(key): key for key in self.REQUIRED_OBSERVATION_KEYS
        }
        for alias_key, canonical_key in self.OBSERVATION_KEY_ALIASES.items():
            canonical_key_map[self._sanitize_observation_key(alias_key)] = canonical_key

        normalized_required: dict[str, str] = {}
        extra_observations: dict[str, str] = {}

        for raw_key, raw_value in source.items():
            key_text = str(raw_key or "").strip()
            if not key_text:
                continue

            normalized_key = self._sanitize_observation_key(key_text)
            canonical_key = canonical_key_map.get(normalized_key, key_text)
            value_text = str(raw_value).strip() if raw_value is not None else self.DEFAULT_OBSERVATION_VALUE
            if not value_text:
                value_text = self.DEFAULT_OBSERVATION_VALUE

            if canonical_key in self.REQUIRED_OBSERVATION_KEYS:
                normalized_required[canonical_key] = value_text
            else:
                extra_observations[canonical_key] = value_text

        ordered_observations: dict[str, str] = {}
        for key in self.REQUIRED_OBSERVATION_KEYS:
            ordered_observations[key] = normalized_required.get(key, self.DEFAULT_OBSERVATION_VALUE)

        for key, value in extra_observations.items():
            if key not in ordered_observations:
                ordered_observations[key] = value

        return ordered_observations

    def _build_fallback_payload_from_text(self, raw_text: str, person_name: str | None = None) -> dict[str, Any]:
        text = str(raw_text or "")
        uppercase_text = text.upper()

        result_match = re.search(r"\b(MISMATCH|INCONCLUSIVE|MATCH)\b", uppercase_text)
        inferred_result = result_match.group(1) if result_match else "INCONCLUSIVE"

        confidence_raw: Any = None
        confidence_match = re.search(
            r'(?i)(?:"?(?:confidence|score)"?\s*[:=]\s*"?)(\d+(?:\.\d+)?)\s*(%?)',
            text,
        )
        if confidence_match:
            confidence_raw = confidence_match.group(1) + confidence_match.group(2)

        reason = ""
        reason_match = re.search(r'(?is)"reason"\s*:\s*"((?:\\.|[^"])*)"', text)
        if reason_match:
            reason = reason_match.group(1).replace('\\"', '"').strip()

        if not reason:
            reason = "Model response was not valid JSON. Fallback parsing logic was applied."

        return {
            "is_match": inferred_result == "MATCH",
            "result": inferred_result,
            "confidence": confidence_raw,
            "matched_person": person_name if inferred_result == "MATCH" and person_name else None,
            "reason": reason,
            "observations": {},
        }

    def _normalize_response_payload(
        self,
        payload: dict[str, Any],
        raw_text: str,
        person_name: str | None = None,
    ) -> dict[str, Any]:
        normalized_payload = dict(payload)

        result = self._normalize_result_value(normalized_payload)
        confidence = self._normalize_confidence_value(normalized_payload.get("confidence"), result)
        reason = str(normalized_payload.get("reason", "") or "").strip()
        if not reason:
            reason = "No reasoning text was provided by the model."

        observations = self._normalize_observations(normalized_payload.get("observations"))
        matched_person = self._normalize_matched_person_value(
            normalized_payload.get("matched_person"),
            person_name,
            result,
        )

        normalized_payload["is_match"] = result == "MATCH"
        normalized_payload["result"] = result
        normalized_payload["verdict"] = result
        normalized_payload["confidence"] = confidence
        normalized_payload["matched_person"] = matched_person
        normalized_payload["reason"] = reason
        normalized_payload["observations"] = observations
        normalized_payload["raw_response"] = raw_text

        return normalized_payload

    def _parse_and_normalize_response(self, raw_text: str, person_name: str | None = None) -> dict[str, Any]:
        for candidate in self._iter_json_candidates(raw_text):
            parsed_candidate = self._parse_json_candidate(candidate)
            if isinstance(parsed_candidate, dict):
                return self._normalize_response_payload(parsed_candidate, raw_text, person_name)

        self.logger.warning("Gemini response was not valid JSON. Applying fallback parser.")
        fallback_payload = self._build_fallback_payload_from_text(raw_text, person_name)
        return self._normalize_response_payload(fallback_payload, raw_text, person_name)

    def verify_signatures(
        self,
        reference_image_path: str,
        submitted_image_path: str,
        person_name: str | None = None,
        mode: str | None = None,
    ) -> dict:
        if not os.path.exists(reference_image_path):
            raise FileNotFoundError(f"Reference image not found: {reference_image_path}")
        if not os.path.exists(submitted_image_path):
            raise FileNotFoundError(f"Submitted image not found: {submitted_image_path}")

        image_utils = ImageUtils()
        reference_quality = image_utils.assess_quality(reference_image_path)
        submitted_quality = image_utils.assess_quality(submitted_image_path)

        if reference_quality.overall == "Low":
            self.logger.warning("Reference image quality is low: %s", reference_quality.resolution_detail)
        if submitted_quality.overall == "Low":
            self.logger.warning("Submitted image quality is low: %s", submitted_quality.resolution_detail)

        resized_reference_path = reference_image_path
        resized_submitted_path = submitted_image_path

        try:
            resized_reference_path = image_utils.resize_for_api(reference_image_path)
            resized_submitted_path = image_utils.resize_for_api(submitted_image_path)

            ref_image_bytes, ref_mime_type = self._read_image_bytes_with_mime(resized_reference_path)
            sub_image_bytes, sub_mime_type = self._read_image_bytes_with_mime(resized_submitted_path)

            reference_sha = hashlib.sha256(ref_image_bytes).hexdigest()
            submitted_sha = hashlib.sha256(sub_image_bytes).hexdigest()

            if reference_sha == submitted_sha:
                self.logger.warning(
                    "Reference and submitted image bytes are identical. mode=%s path1=%s path2=%s",
                    str(mode or "").upper() or "UNKNOWN",
                    reference_image_path,
                    submitted_image_path,
                )

            self.logger.info(
                "Prepared Gemini payload mode=%s ref=%s(%s) sub=%s(%s)",
                str(mode or "").upper() or "UNKNOWN",
                Path(reference_image_path).name,
                ref_mime_type,
                Path(submitted_image_path).name,
                sub_mime_type,
            )

            input_manifest = self._build_input_manifest_prompt(
                mode=mode,
                reference_name=Path(reference_image_path).name,
                submitted_name=Path(submitted_image_path).name,
                reference_hash=reference_sha,
                submitted_hash=submitted_sha,
            )
            prompt = f"{input_manifest}\n\n{self._build_forensic_prompt(person_name)}"

            from google import genai
            from google.genai import types

            google_api_error_type: Any = Exception
            try:
                api_core_exceptions = importlib.import_module("google.api_core.exceptions")
                google_api_error_type = getattr(api_core_exceptions, "GoogleAPIError", Exception)
            except Exception:
                google_api_error_type = Exception

            model_name = self._get_model()
            client = genai.Client(api_key=self._get_api_key())

            def _call_gemini_api(prompt_text: str, include_images: bool = True):
                contents = []
                if include_images:
                    contents.extend(
                        [
                            types.Part.from_text(text="Image 1: REFERENCE signature"),
                            types.Part.from_bytes(data=ref_image_bytes, mime_type=ref_mime_type),
                            types.Part.from_text(text="Image 2: SUBMITTED or QUESTIONED signature"),
                            types.Part.from_bytes(data=sub_image_bytes, mime_type=sub_mime_type),
                        ]
                    )
                contents.append(types.Part.from_text(text=prompt_text))

                try:
                    return client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        generation_config={"temperature": 0.1},
                    )
                except TypeError:
                    return client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(temperature=0.1),
                    )

            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_call_gemini_api, prompt, True)
                    response = future.result(timeout=180)

                raw_text = str(getattr(response, "text", "") or "")
                if not raw_text:
                    raise RuntimeError("Gemini returned an empty response. Please try again.")

                self._print_raw_response_to_terminal(raw_text, model_name)

                continuation_round = 0
                max_continuation_rounds = 8

                while self._is_response_truncated(response, raw_text) and continuation_round < max_continuation_rounds:
                    continuation_round += 1
                    self.logger.warning(
                        "Gemini response appears truncated. Requesting continuation chunk %s",
                        continuation_round,
                    )

                    tail_context = raw_text[-8000:]
                    continuation_prompt = (
                        "Continue your previous response from the exact character where it stopped. "
                        "Return only the missing continuation text. "
                        "Do not restart, do not repeat, and do not add explanation.\n\n"
                        "Response tail already received:\n"
                        f"{tail_context}"
                    )

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(_call_gemini_api, continuation_prompt, False)
                        response = future.result(timeout=180)

                    continuation_text = str(getattr(response, "text", "") or "")
                    if not continuation_text:
                        self.logger.warning("Continuation response was empty at round %s", continuation_round)
                        break

                    self._print_raw_response_to_terminal(continuation_text, model_name)
                    raw_text = self._append_with_overlap(raw_text, continuation_text)

                parsed = self._parse_and_normalize_response(raw_text, person_name)

                parsed["raw_response"] = raw_text
                parsed["model_used"] = model_name
                parsed["mode_used"] = str(mode or "").upper() or "UNKNOWN"
                parsed["reference_image_sha256"] = reference_sha
                parsed["submitted_image_sha256"] = submitted_sha
                parsed["reference_quality"] = reference_quality._asdict()
                parsed["submitted_quality"] = submitted_quality._asdict()

                return parsed

            except concurrent.futures.TimeoutError as exc:
                self.logger.exception("Gemini API timeout")
                raise RuntimeError(
                    "Gemini analysis timed out after 180 seconds. Please try again."
                ) from exc
            except google_api_error_type as exc:
                self.logger.exception("Gemini API request failed")
                raise RuntimeError(
                    f"Gemini API error occurred while verifying signatures: {exc}"
                ) from exc
            except JSONDecodeError as exc:
                self.logger.exception("Gemini response JSON parsing failed")
                raise RuntimeError(
                    "Gemini returned an invalid JSON response. Please retry verification."
                ) from exc
            except ValueError as exc:
                self.logger.exception("Gemini response validation failed")
                raise RuntimeError(str(exc)) from exc
            except Exception as exc:
                self.logger.exception("Unexpected Gemini verification error")
                raise RuntimeError(
                    f"Failed to complete Gemini verification: {exc}"
                ) from exc
        finally:
            for path in (resized_reference_path, resized_submitted_path):
                if path and path not in {reference_image_path, submitted_image_path}:
                    try:
                        path_obj = Path(path)
                        if path_obj.exists():
                            path_obj.unlink()
                    except Exception:
                        self.logger.warning("Unable to clean temporary image: %s", path)

    def ping(self) -> tuple[bool, str]:
        try:
            api_key = self._get_api_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            with urllib.request.urlopen(url, timeout=10) as response:
                if int(getattr(response, "status", 0)) == 200:
                    return True, "Connection successful"
            return False, "Network error: unexpected response"
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 403}:
                return False, "Invalid API key"
            return False, f"Network error: HTTP {exc.code}"
        except Exception as exc:
            return False, f"Network error: {exc}"
