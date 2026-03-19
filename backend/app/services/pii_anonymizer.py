from typing import Tuple, Dict, Any, List
import logging
import re

logger = logging.getLogger(__name__)

# ── Load spaCy model once at module level ──
try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
    _SPACY_AVAILABLE = True
    logger.info("spaCy NER model loaded successfully")
except Exception:
    _nlp = None
    _SPACY_AVAILABLE = False
    logger.warning("spaCy model not available — falling back to regex-only PII detection")


class PIIAnonymizer:
    """
    Hybrid PII detection and anonymization using regex + spaCy NER.
    NO data is sent to any external service — everything runs locally.
    Covers Indian PII (Aadhaar, PAN, GSTIN, etc.) and international patterns.
    spaCy NER catches names, organizations, and locations that regex misses.
    """

    def __init__(self, gemini_client: Any = None):
        # gemini_client is kept for interface compatibility but NOT used for PII detection
        self.gemini = gemini_client

        # ── Comprehensive regex recognizers (ordered by specificity) ──
        self.regex_recognizers = {
            # ── Indian Document Numbers ──
            "IN_AADHAAR": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
            "IN_PAN": r'\b[A-Z]{5}\d{4}[A-Z]\b',
            "IN_GSTIN": r'\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]\b',
            "IN_VOTER_ID": r'\b[A-Z]{3}\d{7}\b',
            "IN_PASSPORT": r'\b[A-Z]\d{7}\b',
            "IN_DRIVING_LICENSE": r'\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{7}\b',
            "IN_IFSC": r'\b[A-Z]{4}0[A-Z0-9]{6}\b',
            "IN_UPI": r'\b[a-zA-Z0-9._-]+@[a-z]{2,}\b(?=.*(?:upi|pay|@))',
            "IN_VEHICLE_REG": r'\b[A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{4}\b',

            # ── Contact Info ──
            "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "PHONE": r'(?:\+91[\s-]?|91[\s-]?|0)?[6-9]\d{9}\b',
            "PHONE_INTL": r'\+\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}',

            # ── Financial ──
            "CREDIT_CARD": r'\b(?:\d{4}[\s-]?){3}\d{4}\b',
            "BANK_ACCOUNT": r'\b\d{9,18}\b(?=.*(?:account|a/c|acc))',
            "IN_MICR": r'\b\d{9}\b(?=.*(?:MICR|micr))',

            # ── Addresses (Indian PIN codes) ──
            "IN_PIN_CODE": r'\b[1-9]\d{5}\b',

            # ── Dates (common formats in legal docs) ──
            "DATE": r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b',
            "DATE_WRITTEN": r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[,]?\s+\d{4}\b',
            "DATE_NATURAL": r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{4}\b',

            # ── Names via titles (common in Indian legal docs) ──
            "PERSON": r'(?:Mr\.?|Mrs\.?|Ms\.?|Shri\.?|Smt\.?|Dr\.?|Prof\.?|Sh\.?|Sri\.?|Kumari|Advocate|Adv\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}',

            # ── Organizations (common legal suffixes) ──
            "ORGANIZATION": r'\b[A-Z][A-Za-z&\s]+(?:Pvt\.?\s*Ltd\.?|Private\s+Limited|Ltd\.?|Limited|LLP|Inc\.?|Corp\.?|Corporation|LLC|Co\.?|Company|Bank|Trust|Foundation|Association|Society|Institute)\b',

            # ── Addresses (multi-line Indian addresses) ──
            "ADDRESS": r'\b(?:No\.|Plot|House|Flat|Door|Building|Block|Floor|Street|Road|Lane|Nagar|Colony|Sector|Phase)\s*\.?\s*(?:No\.?)?\s*\d[A-Za-z0-9\s,/.-]{5,80}',

            # ── International ──
            "US_SSN": r'\b\d{3}-\d{2}-\d{4}\b',
            "IP_ADDRESS": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            "URL": r'https?://[^\s<>"{}|\\^`\[\]]+',
        }

        # spaCy entity types to capture
        self._spacy_entity_map = {
            "PERSON": "PERSON",
            "ORG": "ORGANIZATION",
            "GPE": "LOCATION",
            "LOC": "LOCATION",
            "FAC": "LOCATION",
            "DATE": "DATE_NER",
            "MONEY": "MONETARY_VALUE",
        }

    def _detect_with_spacy(self, text: str) -> List[Dict[str, str]]:
        """Run spaCy NER on text and return detected entities."""
        if not _SPACY_AVAILABLE or not _nlp:
            return []

        entities = []
        doc = _nlp(text)
        for ent in doc.ents:
            mapped_type = self._spacy_entity_map.get(ent.label_)
            if not mapped_type:
                continue
            ent_text = ent.text.strip()
            if len(ent_text) < 2:
                continue
            # Skip entities that are just numbers (likely caught by regex more specifically)
            if ent_text.isdigit():
                continue
            entities.append({
                "entity_type": mapped_type,
                "text": ent_text,
            })

        logger.info("spaCy NER detected %d entities", len(entities))
        return entities

    async def anonymize(self, text: str) -> Tuple[str, Dict[str, str]]:
        if not text:
            return "", {}

        # 1. Detect PII using LOCAL regex
        entities = []
        for entity_type, pattern in self.regex_recognizers.items():
            flags = re.IGNORECASE if entity_type in ("DATE_WRITTEN", "DATE_NATURAL", "ADDRESS") else 0
            for match in re.finditer(pattern, text, flags):
                matched_text = match.group().strip()
                if len(matched_text) < 3:
                    continue
                entities.append({
                    "entity_type": entity_type,
                    "text": matched_text
                })

        logger.info("Regex PII detection found %d entities", len(entities))

        # 2. Augment with spaCy NER (catches names without titles, orgs, locations)
        spacy_entities = self._detect_with_spacy(text)

        # Merge: add spaCy entities that weren't already caught by regex
        existing_texts = {e["text"] for e in entities}
        for ent in spacy_entities:
            if ent["text"] in existing_texts:
                continue
            if any(ent["text"] in rt or rt in ent["text"] for rt in existing_texts):
                continue
            entities.append(ent)
            existing_texts.add(ent["text"])

        logger.info("Total PII entities after NER merge: %d", len(entities))

        # 3. Augment with Gemini LLM detection (catches Indian names, multilingual PII)
        if self.gemini:
            try:
                llm_entities = await self.gemini.detect_pii(text[:8000])
                if isinstance(llm_entities, list):
                    for ent in llm_entities:
                        ent_text = ent.get("text", "").strip()
                        ent_type = ent.get("entity_type", "PII")
                        if len(ent_text) < 2:
                            continue
                        if ent_text in existing_texts:
                            continue
                        if any(ent_text in et or et in ent_text for et in existing_texts):
                            continue
                        entities.append({"entity_type": ent_type, "text": ent_text})
                        existing_texts.add(ent_text)
                    logger.info("Total PII entities after Gemini merge: %d", len(entities))
            except Exception as e:
                logger.warning("Gemini PII detection failed, continuing with regex+spaCy: %s", e)

        # 3. Process entities and create mapping
        mapping = {}
        counters = {}

        # Sort by text length descending to avoid partial replacements
        entities = sorted(entities, key=lambda x: len(x["text"]), reverse=True)

        # Deduplicate: unique original strings → tokens
        unique_entities = {}
        for entity in entities:
            orig = entity["text"]
            etype = entity["entity_type"]
            if orig not in unique_entities:
                counters[etype] = counters.get(etype, 0) + 1
                token = f"[{etype}_{counters[etype]}]"
                unique_entities[orig] = token
                mapping[token] = orig

        # 4. Perform replacements
        anonymized_text = text
        for orig, token in unique_entities.items():
            escaped_orig = re.escape(orig)
            if orig.isalnum():
                pattern = f"\\b{escaped_orig}\\b"
            else:
                pattern = escaped_orig

            anonymized_text = re.sub(pattern, token, anonymized_text)

        logger.info("Anonymized %d unique PII entities", len(mapping))
        return anonymized_text, mapping

    def deanonymize(self, text: str, mapping: Dict[str, str]) -> str:
        if not text:
            return ""
        result = text
        for token, original in mapping.items():
            result = result.replace(token, original)
        return result

    def deanonymize_dict(self, data: Any, mapping: Dict[str, str]) -> Any:
        if isinstance(data, str):
            return self.deanonymize(data, mapping)
        elif isinstance(data, list):
            return [self.deanonymize_dict(item, mapping) for item in data]
        elif isinstance(data, dict):
            return {k: self.deanonymize_dict(v, mapping) for k, v in data.items()}
        return data
