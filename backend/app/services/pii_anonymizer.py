from typing import Tuple, Dict, Any, List
import logging
import re

class PIIAnonymizer:
    """
    Handles PII detection, anonymization, and de-anonymization.
    Now uses Gemini for detection, removing the dependency on spaCy.
    """

    def __init__(self, gemini_client: Any = None):
        self.gemini = gemini_client
        # Standard regex for some structured PII as fallback or enhancement
        self.regex_recognizers = {
            "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "IN_AADHAAR": r'\b\d{4}\s?\d{4}\s?\d{4}\b',
            "IN_PAN": r'\b[A-Z]{5}\d{4}[A-Z]\b',
            "PHONE": r'\b(?:\+91|91|0)?[6-9]\d{9}\b'
        }

    async def anonymize(self, text: str) -> Tuple[str, Dict[str, str]]:
        if not text:
            return "", {}
            
        # 1. Use Gemini to find PII
        entities = []
        if self.gemini:
            entities = await self.gemini.detect_pii(text)
        
        # 2. Add regex findings to entities
        for entity_type, pattern in self.regex_recognizers.items():
            for match in re.finditer(pattern, text):
                entities.append({
                    "entity_type": entity_type,
                    "text": match.group()
                })

        # 3. Process entities and create mapping
        mapping = {}
        counters = {}
        
        # Sort by text length descending to avoid partial replacements of same strings
        # (e.g., if we have "John Doe" and "John")
        entities = sorted(entities, key=lambda x: len(x["text"]), reverse=True)
        
        # Unique original strings mapped to tokens
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
        # We need to be careful about overlapping entities. 
        # A safer way is to find all occurrences and replace in one pass if possible,
        # or sort and replace carefully.
        
        anonymized_text = text
        # Replace each unique original string with its token
        for orig, token in unique_entities.items():
            # Use word boundaries if possible, but fallback to simple replace for non-alphanumeric
            # Legal docs have many special characters, so we escape the string
            escaped_orig = re.escape(orig)
            # We use \b for alphanumeric, or just the escaped string if it contains special chars
            if orig.isalnum():
                pattern = f"\\b{escaped_orig}\\b"
            else:
                pattern = escaped_orig
                
            anonymized_text = re.sub(pattern, token, anonymized_text)
            
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
