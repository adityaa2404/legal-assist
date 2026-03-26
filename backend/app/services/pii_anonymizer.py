from typing import Tuple, Dict, Any, List
import logging
import re

logger = logging.getLogger(__name__)

# ── Load Presidio engine once at module level ──
try:
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine

    # Silence noisy "Entity CARDINAL is not mapped" warnings from Presidio
    logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

    _nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }
    _nlp_engine = NlpEngineProvider(nlp_configuration=_nlp_config).create_engine()
    _analyzer = AnalyzerEngine(nlp_engine=_nlp_engine)
    _anonymizer_engine = AnonymizerEngine()

    # Register Indian-specific recognizers that Presidio doesn't have out of the box
    _indian_recognizers = [
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
                r"\b[A-Z][A-Za-z&\s]+(?:Pvt\.?\s*Ltd\.?|Private\s+Limited|Ltd\.?|Limited|LLP)\b",
                0.75,
            )],
        ),
    ]
    for rec in _indian_recognizers:
        _analyzer.registry.add_recognizer(rec)

    logger.info("Presidio analyzer loaded with %d Indian recognizers", len(_indian_recognizers))

except Exception as e:
    _analyzer = None
    _anonymizer_engine = None
    raise RuntimeError(
        f"Presidio is required but failed to load: {e}. "
        "Install with: pip install presidio-analyzer presidio-anonymizer && python -m spacy download en_core_web_lg"
    )


class PIIAnonymizer:
    """
    PII detection and anonymization — fully local, zero data sent externally.

    Engine: Microsoft Presidio (spaCy NER + built-in recognizers)
    + custom Indian pattern recognizers (Aadhaar, PAN, GSTIN, etc.)
    """

    def __init__(self, gemini_client: Any = None):
        # gemini_client accepted for interface compatibility but NEVER used
        pass

    async def anonymize(self, text: str) -> Tuple[str, Dict[str, str]]:
        if not text:
            return "", {}

        return self._anonymize_with_presidio(text)

    # spaCy's default max is 1M chars — chunk large texts to stay under
    SPACY_MAX_CHARS = 900_000

    def _anonymize_with_presidio(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Use Presidio for PII detection — all processing is local.
        Chunks text if it exceeds spaCy's max_length to avoid ValueError."""
        if len(text) > self.SPACY_MAX_CHARS:
            return self._anonymize_chunked(text)

        results = _analyzer.analyze(
            text=text,
            language="en",
            score_threshold=0.4,
        )

        # Deduplicate overlapping detections — keep highest confidence
        results = self._resolve_overlaps(results)

        logger.debug("Presidio detected %d PII entities", len(results))

        # Build mapping and anonymize
        mapping = {}
        counters = {}
        # Process longest matches first to avoid partial replacements
        results = sorted(results, key=lambda r: r.end - r.start, reverse=True)

        unique_entities = {}
        for result in results:
            orig = text[result.start:result.end].strip()
            if len(orig) < 2:
                continue
            if orig in unique_entities:
                continue

            etype = result.entity_type
            counters[etype] = counters.get(etype, 0) + 1
            token = f"[{etype}_{counters[etype]}]"
            unique_entities[orig] = token
            mapping[token] = orig

        # Perform replacements
        anonymized_text = text
        for orig, token in unique_entities.items():
            escaped_orig = re.escape(orig)
            if orig.isalnum():
                pattern = f"\\b{escaped_orig}\\b"
            else:
                pattern = escaped_orig
            anonymized_text = re.sub(pattern, token, anonymized_text)

        logger.debug("Anonymized %d unique PII entities via Presidio", len(mapping))
        return anonymized_text, mapping

    def _anonymize_chunked(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Split text into chunks under spaCy's limit, analyze in parallel, merge.
        Splits on PAGE_BOUNDARY markers to avoid cutting mid-sentence."""
        from concurrent.futures import ThreadPoolExecutor
        import os

        PAGE_SEP = "\n\n<<<<<PAGE_BOUNDARY>>>>>\n\n"
        if PAGE_SEP in text:
            pages = text.split(PAGE_SEP)
        else:
            pages = text.split("\n\n")

        # Group pages into chunks under the limit
        chunks = []
        current_chunk = []
        current_len = 0
        joiner = PAGE_SEP if PAGE_SEP in text else "\n\n"

        for page in pages:
            if current_len + len(page) > self.SPACY_MAX_CHARS and current_chunk:
                chunks.append(joiner.join(current_chunk))
                current_chunk = []
                current_len = 0
            current_chunk.append(page)
            current_len += len(page) + len(joiner)
        if current_chunk:
            chunks.append(joiner.join(current_chunk))

        logger.info("PII: %d chars → %d chunks, analyzing in parallel", len(text), len(chunks))

        # Step 1: Run Presidio analysis on all chunks in parallel (the slow part)
        def _analyze_chunk(chunk):
            results = _analyzer.analyze(text=chunk, language="en", score_threshold=0.4)
            results = self._resolve_overlaps(results)
            # Extract raw entities from chunk
            entities = []
            for r in sorted(results, key=lambda r: r.end - r.start, reverse=True):
                orig = chunk[r.start:r.end].strip()
                if len(orig) >= 2:
                    entities.append((orig, r.entity_type))
            return entities

        max_workers = min(len(chunks), max(2, os.cpu_count() or 2))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            chunk_entities = list(executor.map(_analyze_chunk, chunks))

        # Step 2: Build unified mapping (sequential — fast)
        all_mapping = {}
        reverse_map = {}  # orig_text → token (for dedup across chunks)
        counters = {}

        for entities in chunk_entities:
            for orig, etype in entities:
                if orig not in reverse_map:
                    counters[etype] = counters.get(etype, 0) + 1
                    token = f"[{etype}_{counters[etype]}]"
                    reverse_map[orig] = token
                    all_mapping[token] = orig

        # Step 3: Apply replacements to each chunk (parallelizable)
        def _replace_chunk(chunk_idx):
            chunk = chunks[chunk_idx]
            entities = chunk_entities[chunk_idx]
            seen = {}
            for orig, _ in entities:
                if orig not in seen:
                    seen[orig] = reverse_map[orig]
            anonymized = chunk
            for orig, token in seen.items():
                escaped = re.escape(orig)
                pattern = f"\\b{escaped}\\b" if orig.isalnum() else escaped
                anonymized = re.sub(pattern, token, anonymized)
            return anonymized

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            anonymized_chunks = list(executor.map(_replace_chunk, range(len(chunks))))

        anonymized_text = joiner.join(anonymized_chunks)
        logger.info("PII done: %d entities across %d chunks", len(all_mapping), len(chunks))
        return anonymized_text, all_mapping

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
        # Sort tokens by length DESCENDING so [LOCATION_10] is replaced
        # before [LOCATION_1] — prevents partial match corruption.
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
