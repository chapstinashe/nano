"""Hybrid retrieval scoring shared by Cosmos retrieval and guest chunk reranking."""

import re
from difflib import SequenceMatcher

from app.core.config import Config

_STOPWORDS = {
    "about", "after", "also", "been", "being", "both", "could", "from", "have",
    "into", "more", "only", "other", "shall", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "those", "through", "very",
    "were", "what", "when", "where", "which", "while", "will", "with", "would",
    "your", "does", "do", "did", "how", "why", "who", "can", "should", "would",
    "name", "called", "named",
}


def normalize_query(query: str) -> str:
    """Normalize whitespace and fix common question typos (e.g. mane -> name)."""
    text = re.sub(r"\s+", " ", (query or "").strip())
    if not text:
        return ""

    if re.search(r"(?i)\bwhat(?:'s| is| was)\s", text) or text.lower().endswith(" mane"):
        text = re.sub(r"(?i)\bmane\b", "name", text)

    return text.strip()


def build_query_variants(query: str) -> list[str]:
    normalized = normalize_query(query)
    if not normalized:
        return []

    variants: list[str] = [normalized]

    if normalized.endswith("?"):
        statement = normalized.rstrip("?").strip()
        if statement and statement not in variants:
            variants.append(statement)

    tokens = [
        word
        for word in re.findall(r"[a-z0-9]+", normalized.lower())
        if len(word) > 2 and word not in _STOPWORDS
    ]
    if tokens:
        keyword_query = " ".join(dict.fromkeys(tokens))
        if keyword_query and keyword_query not in variants:
            variants.append(keyword_query)

    focus_terms = extract_focus_terms(normalized)
    if focus_terms:
        focus_query = " ".join(focus_terms)
        if focus_query and focus_query not in variants:
            variants.append(focus_query)

    if len(tokens) >= 4:
        focus = " ".join(tokens[:6])
        if focus not in variants:
            variants.append(focus)

    return variants


def extract_focus_terms(query: str) -> list[str]:
    normalized = normalize_query(query).lower().strip()
    terms: list[str] = []

    patterns = [
        r"(?:what (?:is|was)|what's) (?:the )?name of (?:the )?([a-z0-9 -]+?)(?:\?|$)",
        r"(?:what (?:is|was)|what's) (?:the )?([a-z0-9 -]+?) name(?:\?|$)",
        r"(?:name of (?:the )?)([a-z0-9 -]+?)(?:\?|$)",
        r"(?:who is (?:the )?)([a-z0-9 -]+?)(?:\?|$)",
        r"(?:what (?:is|was)|what's) (?:the )?([a-z0-9 -]+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            subject = match.group(1).strip()
            if subject:
                terms.extend(_tokenize(subject))
            break

    terms.extend(_tokenize(normalized))
    return list(dict.fromkeys(terms))


def _tokenize(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(word) > 2 and word not in _STOPWORDS
    ]


def _lexical_overlap(query: str, text: str) -> float:
    query_tokens = set(_tokenize(query))
    text_tokens = set(_tokenize(text))
    if not query_tokens or not text_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def _phrase_overlap(query: str, text: str) -> float:
    query_lower = normalize_query(query).lower()
    text_lower = (text or "").lower()
    words = re.findall(r"[a-z0-9]+", query_lower)
    if len(words) < 2:
        return 0.0

    hits = 0
    checks = 0
    for size in (3, 2):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i : i + size])
            if len(phrase) < 6:
                continue
            checks += 1
            if phrase in text_lower:
                hits += 1
    return hits / checks if checks else 0.0


def _fuzzy_overlap(query: str, text: str) -> float:
    return SequenceMatcher(None, normalize_query(query).lower(), (text or "")[:1200].lower()).ratio()


def _is_name_question(query: str) -> bool:
    normalized = normalize_query(query).lower()
    return bool(
        re.search(r"\bwhat(?:'s| is| was) (?:the )?name of\b", normalized)
        or re.search(r"\bname of (?:the )?\w+", normalized)
        or re.search(r"\bwhat(?:'s| is| was) (?:the )?[\w -]+ name\b", normalized)
        or re.search(r"\b(?:what|who) (?:is|was) (?:the )?[\w -]+'?s? name\b", normalized)
    )


def _proper_name_tokens(text: str) -> list[str]:
    return re.findall(r"\b[A-Z][a-z]{2,}(?:[a-z]+)?\b", text or "")


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [part.strip() for part in parts if len(part.strip()) > 12]


def _answer_pattern_score_single(query: str, text: str) -> float:
    if not text.strip():
        return 0.0

    score = 0.0
    focus_terms = extract_focus_terms(query)

    if _is_name_question(query):
        naming_patterns = [
            r"\b(?:the|a)\s+dragon(?:'s|s)?\s+name\s+(?:was|is)\s+[A-Za-z]",
            r"\b(?:name|called|named)\s+(?:was|is)\s+[A-Za-z][A-Za-z'-]{2,}\b",
            r"\b(?:his|her|its)\s+name\s+(?:was|is)\b",
            r"\bknown\s+as\s+[A-Za-z][A-Za-z'-]{2,}\b",
            r"\bcalled\s+(?:him|her|it|the)\s+[A-Za-z][A-Za-z'-]{2,}\b",
            r"\bname\s+was\s+[A-Za-z][A-Za-z'-]{2,}\s*,\s*last of\b",
        ]
        for pattern in naming_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += 0.45

        for term in focus_terms:
            if len(term) < 4:
                continue
            escaped = re.escape(term)
            appositive_patterns = [
                rf"\b[A-Za-z][A-Za-z'-]{{2,}}\s*,\s*(?:the|a)\s+{escaped}\b",
                rf"(?:the|a)\s+{escaped}\s*,\s*[A-Za-z][A-Za-z'-]{{2,}}\b",
                rf"(?:the|a)\s+{escaped}\s+[A-Za-z][A-Za-z'-]{{2,}}\b",
                rf"\b[A-Za-z][A-Za-z'-]{{2,}}\s+(?:the|a)\s+{escaped}\b",
            ]
            for pattern in appositive_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    score += 0.35
                    break

        sentence_lower = text.lower()
        if any(term in sentence_lower for term in focus_terms if len(term) >= 4):
            if re.search(r"\b(?:name|called|named|known as)\b", text, re.IGNORECASE):
                score += 0.25

    if re.search(r"\b(?:who is|who was)\b", query, re.IGNORECASE):
        if _lexical_overlap(query, text) >= 0.4 and _proper_name_tokens(text):
            score += 0.3

    return min(score, 1.0)


def answer_pattern_score(query: str, text: str) -> float:
    """Boost passages that look like direct answers to factual questions."""
    query = normalize_query(query)
    if not text.strip():
        return 0.0

    sentences = _split_sentences(text)
    if not sentences:
        return _answer_pattern_score_single(query, text)

    return max(_answer_pattern_score_single(query, sentence) for sentence in sentences)


def _action_scene_penalty(query: str, text: str) -> float:
    """Penalize battle/action chunks for name questions when they lack naming evidence."""
    if not _is_name_question(query):
        return 0.0
    if answer_pattern_score(query, text) >= 0.35:
        return 0.0

    action_signals = (
        r"\berupted\b",
        r"\bbattlefield\b",
        r"\bsoldiers\b",
        r"\barrows\b",
        r"\bfled\b",
        r"\bcrashed\b",
        r"\bbled\b",
        r"\broar\b",
        r"\bstormed\b",
        r"\bflame\b",
    )
    hits = sum(1 for pattern in action_signals if re.search(pattern, text, re.IGNORECASE))
    if hits >= 2:
        return min(0.45, 0.1 * hits)
    return 0.0


def score_result(query: str, vector_score: float, text: str) -> tuple[float, dict[str, float]]:
    query = normalize_query(query)
    lexical = _lexical_overlap(query, text)
    phrase = _phrase_overlap(query, text)
    fuzzy = _fuzzy_overlap(query, text)
    answer_pattern = answer_pattern_score(query, text)
    penalty = _action_scene_penalty(query, text)

    if _is_name_question(query):
        vector_weight = Config.RETRIEVAL_VECTOR_WEIGHT * 0.5
        pattern_weight = Config.RETRIEVAL_ANSWER_PATTERN_WEIGHT * 2.5
    else:
        vector_weight = Config.RETRIEVAL_VECTOR_WEIGHT
        pattern_weight = Config.RETRIEVAL_ANSWER_PATTERN_WEIGHT

    combined = (
        (vector_score * vector_weight)
        + (lexical * Config.RETRIEVAL_LEXICAL_WEIGHT)
        + (phrase * Config.RETRIEVAL_PHRASE_WEIGHT)
        + (fuzzy * Config.RETRIEVAL_FUZZY_WEIGHT)
        + (answer_pattern * pattern_weight)
        - penalty
    )
    breakdown = {
        "vector_score": round(vector_score, 4),
        "lexical_overlap": round(lexical, 4),
        "phrase_overlap": round(phrase, 4),
        "fuzzy_overlap": round(fuzzy, 4),
        "answer_pattern": round(answer_pattern, 4),
        "action_penalty": round(penalty, 4),
        "retrieval_score": round(combined, 4),
    }
    return round(combined, 4), breakdown


def distance_to_similarity(distance: float) -> float:
    return max(0.0, min(1.0, 1.0 - (float(distance) / 2.0)))
