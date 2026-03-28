from typing import Tuple, Dict, Any, List
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

# ── Load Presidio with pattern recognizers only (no spaCy model needed) ──
try:
    from presidio_analyzer import PatternRecognizer, Pattern, RecognizerResult
    from presidio_anonymizer import AnonymizerEngine

    _anonymizer_engine = AnonymizerEngine()

    # Indian-specific recognizers
    _recognizers = [
        PatternRecognizer(
            supported_entity="IN_AADHAAR",
            patterns=[Pattern("aadhaar", r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", 0.85)],
        ),
        PatternRecognizer(
            supported_entity="IN_PAN",
            patterns=[Pattern("pan", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0.9)],
        ),
        PatternRecognizer(
            supported_entity="IN_GSTIN",
            patterns=[Pattern("gstin", r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]\b", 0.95)],
        ),
        PatternRecognizer(
            supported_entity="IN_VOTER_ID",
            patterns=[Pattern("voter_id", r"\b[A-Z]{3}\d{7}\b", 0.7)],
        ),
        PatternRecognizer(
            supported_entity="IN_PASSPORT",
            patterns=[Pattern("passport", r"\b[A-Z]\d{7}\b", 0.6)],
        ),
        PatternRecognizer(
            supported_entity="IN_DRIVING_LICENSE",
            patterns=[Pattern("dl", r"\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{7}\b", 0.8)],
        ),
        PatternRecognizer(
            supported_entity="IN_IFSC",
            patterns=[Pattern("ifsc", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", 0.85)],
        ),
        PatternRecognizer(
            supported_entity="IN_VEHICLE_REG",
            patterns=[Pattern("vehicle", r"\b[A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{4}\b", 0.6)],
        ),
        PatternRecognizer(
            supported_entity="IN_PIN_CODE",
            patterns=[Pattern("pincode", r"\b[1-9]\d{5}\b", 0.4)],
        ),
        PatternRecognizer(
            supported_entity="PERSON",
            patterns=[Pattern(
                "indian_title_name",
                r"(?:Mr\.?|Mrs\.?|Ms\.?|Shri\.?|Smt\.?|Dr\.?|Prof\.?|Sh\.?|Sri\.?|Kumari|Advocate|Adv\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}",
                0.8,
            )],
        ),
        PatternRecognizer(
            supported_entity="ORGANIZATION",
            patterns=[Pattern(
                "indian_org",
                r"\b[A-Z][A-Za-z&\s]+(?:Pvt\.?\s*Ltd\.?|Private\s+Limited|Ltd\.?|Limited|LLP|Inc\.?|Corp\.?)\b",
                0.75,
            )],
        ),
        # Standard PII patterns
        PatternRecognizer(
            supported_entity="EMAIL_ADDRESS",
            patterns=[Pattern("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", 0.9)],
        ),
        PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            patterns=[
                Pattern("in_phone", r"(?:\+91[\s-]?)?[6-9]\d{9}\b", 0.7),
                Pattern("phone_intl", r"\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}\b", 0.6),
            ],
        ),
        PatternRecognizer(
            supported_entity="CREDIT_CARD",
            patterns=[Pattern("cc", r"\b(?:\d{4}[\s-]?){3}\d{4}\b", 0.6)],
        ),
        PatternRecognizer(
            supported_entity="IP_ADDRESS",
            patterns=[Pattern("ip", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", 0.5)],
        ),
    ]

    logger.info("Presidio loaded: %d pattern recognizers (no spaCy model)", len(_recognizers))

except Exception as e:
    _anonymizer_engine = None
    _recognizers = []
    raise RuntimeError(
        f"Presidio failed to load: {e}. "
        "Install with: pip install presidio-analyzer presidio-anonymizer"
    )


class PIIAnonymizer:
    """
    PII detection and anonymization using Presidio pattern recognizers.
    No spaCy model loaded — pure regex patterns, ~0MB overhead.
    """

    def __init__(self):
        pass

    async def anonymize(self, text: str, timeout: float = 60.0) -> Tuple[str, Dict[str, str]]:
        if not text:
            return "", {}
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._anonymize_with_presidio, text),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error("PII anonymization timed out after %.0fs on %d chars", timeout, len(text))
            return text, {}  # Fail-open: text still protected by anonymized placeholders in prompts

    def _anonymize_with_presidio(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Run all pattern recognizers on text, then build token mapping."""
        # Collect detections from all recognizers
        all_results: List[RecognizerResult] = []
        for recognizer in _recognizers:
            try:
                results = recognizer.analyze(
                    text=text,
                    entities=[recognizer.supported_entities[0]],
                )
                all_results.extend(results)
            except Exception as e:
                logger.debug("Recognizer %s failed: %s", recognizer.supported_entities[0], e)

        # Filter by score threshold
        all_results = [r for r in all_results if r.score >= 0.4]

        # Deduplicate overlapping detections — keep highest confidence
        all_results = self._resolve_overlaps(all_results)

        logger.debug("Presidio detected %d PII entities", len(all_results))

        # Build mapping and anonymize
        mapping = {}
        counters = {}
        unique_entities = {}

        results_sorted = sorted(all_results, key=lambda r: r.end - r.start, reverse=True)
        for result in results_sorted:
            orig = text[result.start:result.end].strip()
            if len(orig) < 2 or orig in unique_entities:
                continue

            etype = result.entity_type
            counters[etype] = counters.get(etype, 0) + 1
            token = f"[{etype}_{counters[etype]}]"
            unique_entities[orig] = token
            mapping[token] = orig

        # Single-pass replacement: one compiled regex instead of N sequential re.sub calls
        anonymized_text = text
        if unique_entities:
            sorted_entities = sorted(unique_entities.keys(), key=len, reverse=True)
            combined = "|".join(
                (f"\\b{re.escape(orig)}\\b" if orig[0].isalnum() and orig[-1].isalnum() else re.escape(orig))
                for orig in sorted_entities
            )
            compiled = re.compile(combined)
            anonymized_text = compiled.sub(lambda m: unique_entities[m.group()], text)

        logger.info("PII: anonymized %d unique entities via Presidio patterns", len(mapping))
        return anonymized_text, mapping

    def _resolve_overlaps(self, results) -> list:
        """Remove overlapping detections, keeping the highest confidence one."""
        if not results:
            return []
        sorted_results = sorted(results, key=lambda r: (r.start, -r.score))
        filtered = [sorted_results[0]]
        for current in sorted_results[1:]:
            prev = filtered[-1]
            if current.start < prev.end:
                if current.score > prev.score:
                    filtered[-1] = current
            else:
                filtered.append(current)
        return filtered

    def deanonymize(self, text: str, mapping: Dict[str, str]) -> str:
        if not text or not mapping:
            return text or ""
        result = text
        for token in sorted(mapping.keys(), key=len, reverse=True):
            result = result.replace(token, mapping[token])
        return result

    def deanonymize_dict(self, data: Any, mapping: Dict[str, str]) -> Any:
        if isinstance(data, str):
            return self.deanonymize(data, mapping)
        elif isinstance(data, list):
            return [self.deanonymize_dict(item, mapping) for item in data]
        elif isinstance(data, dict):
            return {k: self.deanonymize_dict(v, mapping) for k, v in data.items()}
        return data
