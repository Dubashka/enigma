"""MD text anonymization and restoration logic.

Detects PII entities using Natasha (PER, ORG) + Presidio (email, phone, IP)
+ regex (contract numbers, dates, legal entities, person names with initials, addresses).
User-defined extra terms are masked after automatic detection.
Mapping JSON allows full restoration.

anonymize() accepts an optional predetected_entities argument — if provided,
detect_entities() is NOT called again (used when Ollama was already run manually).
"""
from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# Regex patterns for structured PII
# ---------------------------------------------------------------------------

_ORG_OPEN  = r'[«"]'
_ORG_CLOSE = r'[»"]'

_ORG_PREFIXES = ("ООО", "ОАО", "ЗАО", "АО", "ПАО", "ИП", "НКО", "ФГУП", "ГУП", "АНО")
_ORG_PREFIX_RE = "|".join(_ORG_PREFIXES)

_C  = r'[А-ЯЁ]'
_cl = r'[а-яё]'

# ---------------------------------------------------------------------------
# Address building blocks
# ---------------------------------------------------------------------------

_STREET_KW = (
    r'(?:ул(?:\.|[и]ца)'
    r'|пр(?:\.|[о]спект)'
    r'|пер(?:\.|[е]улок)'
    r'|наб(?:\.|[е]режная)'
    r'|шоссе'
    r'|пл(?:\.|[о]щадь)'
    r'|б(?:-р|ульвар)'
    r'|проезд'
    r'|тупик)'
)
_STREET_NAME = r'[А-ЯЁа-яё0-9][\wа-яёА-ЯЁ\-]*(?:\s+[А-ЯЁа-яё0-9][\wа-яёА-ЯЁ\-]*){0,3}'
_HOUSE      = r'(?:,?\s*д(?:\.|[о]м\.?)\s*\d+[\w\-/]*)'
_HOUSE_BARE = r',?\s*д(?:\.|[о]м\.?)\s*\d+[\w\-/]*'
_BLDG       = r'(?:,?\s*(?:к(?:\.|[о]рп\.?)|стр(?:\.?)?)\s*\d+[\w\-/]*)'
_FLAT       = r'(?:,?\s*(?:кв(?:\.|[а]рт\.?)|оф(?:\.)?)\s*\d+)'
_CITY_KW   = r'(?:г(?:\.|[о]род)|п(?:\.|[о]с(?:\.|[е]лок))|с(?:\.|[е]ло)|д(?:\.|[е]ревня))'
_CITY_NAME = r'[А-ЯЁ][а-яёА-ЯЁ\-]+(?:-[А-ЯЁ][а-яёА-ЯЁ\-]+)*'

_MONTH_NAME = (
    r'(?:января|январе|январь'
    r'|февраля|феврале|февраль'
    r'|марта|марте|март'
    r'|апреля|апреле|апрель'
    r'|мая|мае|май'
    r'|июня|июне|июнь'
    r'|июля|июле|июль'
    r'|августа|августе|август'
    r'|сентября|сентябре|сентябрь'
    r'|октября|октябре|октябрь'
    r'|ноября|ноябре|ноябрь'
    r'|декабря|декабре|декабрь)'
)

# Word-boundary для кириллицы: \b не работает с кириллицей,
# поэтому используем негативный lookbehind и lookahead.
_ORG_WORD_START = r'(?<![\u0400-\u04FF\w])'
_ORG_WORD_END   = r'(?![\u0400-\u04FF\w])'

_PATTERNS: list[tuple[str, str]] = [
    ("EMAIL", r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'),
    ("\u0422\u0415\u041b\u0415\u0424\u041e\u041d", r'(?<!\d)(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)'),
    ("IP", r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    (
        "\u041e\u0420\u0413",
        # Префикс типа "ИП", "ООО" и т.д. — только как отдельное слово,
        # не как часть другого слова ("организации", "принципы")
        _ORG_WORD_START
        + r'(?:' + _ORG_PREFIX_RE + r')'
        + _ORG_WORD_END
        + r'(?:'
        + r'\s+' + _ORG_OPEN + r'[А-ЯЁа-яёA-Za-z0-9][\w\s\-]*?' + _ORG_CLOSE
        + r'|\s+[А-ЯЁ][а-яёА-ЯЁ\w\-]{1,40}(?:\s+[А-ЯЁ][а-яёА-ЯЁ\w\-]{1,40}){0,3}'
        + r')?',
    ),
    # ФИО с инициалами — высокая точность, не фильтруем
    ("\u0424\u0418\u041e", _C + _cl + r'+\s+' + _C + r'\.' + _C + r'\.'),
    ("\u0424\u0418\u041e", _C + r'\.' + _C + r'\.\s+' + _C + _cl + r'+'),
    # Полное ФИО (Три слова) — ТОЛЬКО на отдельной строке
    ("\u0424\u0418\u041e", r'[А-ЯЁ][а-яё]{3,}\s+[А-ЯЁ][а-яё]{3,}\s+[А-ЯЁ][а-яё]{3,}'),
    # ---- АДРЕС ----
    (
        "\u0410\u0414\u0420\u0415\u0421",
        _CITY_KW + r'\s+' + _CITY_NAME + r',\s*'
        + _STREET_KW + r'\s+' + _STREET_NAME
        + _HOUSE + r'?' + _BLDG + r'?' + _FLAT + r'?',
    ),
    (
        "\u0410\u0414\u0420\u0415\u0421",
        _STREET_KW + r'\s+' + _STREET_NAME + r',\s*'
        + _HOUSE_BARE + _BLDG + r'?' + _FLAT + r'?',
    ),
    ("\u0414\u041e\u0413\u041e\u0412\u041e\u0420", r'№\s?\d+[\-/\d]*'),
    ("\u0414\u0410\u0422\u0410", r'\b(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\b'),
    ("\u0414\u0410\u0422\u0410", r'(?:«\d{1,2}»|"\d{1,2}"|\b\d{1,2})\s+' + _MONTH_NAME + r'\s+\d{4}(?:\s*г\.?)?'),
]

# ---------------------------------------------------------------------------
# Стоп-слова
# ---------------------------------------------------------------------------

_GEO_STOPWORDS: frozenset[str] = frozenset({
    "москва", "санкт-петербург", "петербург", "новосибирск", "екатеринбург",
    "казань", "нижний", "новгород", "челябинск", "самара", "омск",
    "ростов", "уфа", "красноярск", "пермь", "воронеж", "волгоград",
    "краснодар", "саратов", "тюмень", "тольятти", "ижевск",
    "барнаул", "ульяновск", "иркутск", "хабаровск", "ярославль",
    "владивосток", "махачкала", "томск", "оренбург", "кемерово",
    "россия", "рф", "беларусь", "украина", "казахстан",
    "улица", "проспект", "переулок", "бульвар", "площадь",
    "район", "область", "край", "округ", "республика",
})

# ОРГ-стоп-список: нарицательные слова, которые Natasha часто
# выдаёт за названия организаций (ORG). Малый регистр.
_ORG_COMMON_WORDS: frozenset[str] = frozenset({
    # Роли сторон в договорах
    "заказчик", "заказчика", "заказчику", "заказчиком",
    "исполнитель", "исполнителя", "исполнителю",
    "подрядчик", "подрядчика", "подрядчику",
    "покупатель", "поставщик", "арендодатель", "арендатор",
    "сторона", "стороны", "стороне",
    # Документы
    "доверенность", "доверенности", "доверенностю",
    "доверенностью",
    "договор", "договора", "договору", "договором",
    "соглашение", "соглашения", "приложение",
    "акт", "счет", "заключение",
    # Работы / услуги
    "работа", "работы", "работам",
    "услуга", "услуги", "услугам",
    "заказ", "заказа", "заказу", "заказом",
    "поставка", "оплата",
    # Оргструктура
    "отдел", "департамент", "управление", "служба",
    "центр", "компания", "организация", "предприятие",
    "подразделение", "филиал",
    # Должности
    "руководитель", "директор", "менеджер",
    "сотрудник", "работник", "специалист",
    "председатель", "заместитель", "начальник",
    # Проект
    "проект", "программа", "проекты",
    "клиент", "партнер", "контрагент",
})

# ФИО-паттерны, требующие проверки (полное ФИО без инициалов)
_FIO_STRICT_PATTERNS: frozenset[str] = frozenset({
    r'[А-ЯЁ][а-яё]{3,}\s+[А-ЯЁ][а-яё]{3,}\s+[А-ЯЁ][а-яё]{3,}',
})


def _is_geo_word(word: str) -> bool:
    return word.lower() in _GEO_STOPWORDS


def _is_org_common_word(word: str) -> bool:
    return word.lower() in _ORG_COMMON_WORDS


def _is_short_line_match(text: str, match_start: int, match_end: int) -> bool:
    """Труе если совпадение занимает всю строку (или почти всю)."""
    line_start = text.rfind("\n", 0, match_start)
    line_start = 0 if line_start == -1 else line_start + 1
    line_end = text.find("\n", match_end)
    line_end = len(text) if line_end == -1 else line_end
    line = text[line_start:line_end].strip()
    match_text = text[match_start:match_end]
    return line == match_text


def _all_words_capitalized(text: str) -> bool:
    words = text.split()
    return all(w[0].isupper() for w in words if w)


_NER_PREFIX = "Работник "
_NER_PREFIX_LEN = len(_NER_PREFIX)


def _extract_org_core(org_value: str) -> str | None:
    value = org_value.strip()
    for prefix in sorted(_ORG_PREFIXES, key=len, reverse=True):
        if value.upper().startswith(prefix):
            value = value[len(prefix):].strip()
            break
    if not value:
        return None
    value = re.sub(r'[«"]|[»"]', "", value).strip()
    if re.match(r'^[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.){1,2}\s*$', value):
        return None
    if re.match(r'^[А-ЯЁA-Z]', value) and len(value) >= 3:
        return value
    return None


def _org_stem(name: str) -> str:
    endings = ["овой", "овый", "евой", "евый", "еской", "еский",
               "овое", "евое", "еское",
               "ами", "ах", "ом", "ой", "ого",
               "ем", "ей", "его",
               "ю", "я", "е", "и", "у", "а"]
    word = name.split()[0]
    lower = word.lower()
    for ending in endings:
        if lower.endswith(ending) and len(lower) - len(ending) >= 4:
            return lower[: len(lower) - len(ending)]
    return lower


def _expand_org_spans(
    text: str,
    spans: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    extra: list[tuple[int, int, str, str]] = []
    existing_starts = {s[0] for s in spans}
    org_spans = [s for s in spans if s[2] == "ОРГ"]
    if not org_spans:
        return spans
    seen_cores: set[str] = set()
    for _, _, _, value in org_spans:
        core = _extract_org_core(value)
        if not core or core.lower() in seen_cores:
            continue
        seen_cores.add(core.lower())
        stem = _org_stem(core)
        if len(stem) < 4:
            continue
        pattern = r'(?<![\wа-яёА-ЯЁA-Za-z])' + re.escape(stem) + r'[а-яёА-ЯЁA-Za-z]*(?![\wа-яёА-ЯЁA-Za-z])'
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if m.start() not in existing_starts:
                extra.append((m.start(), m.end(), "ОРГ", m.group()))
                existing_starts.add(m.start())
    return spans + extra


def _regex_entities(text: str) -> list[tuple[int, int, str, str]]:
    found: list[tuple[int, int, str, str]] = []
    for label, pattern in _PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            val = m.group()
            if label == "ФИО" and pattern in _FIO_STRICT_PATTERNS:
                # Полное ФИО без инициалов: только на отдельной строке
                if not _is_short_line_match(text, m.start(), m.end()):
                    continue
                if any(_is_geo_word(w) for w in val.split()):
                    continue
            found.append((m.start(), m.end(), label, val))
    return found


def _natasha_entities(text: str) -> list[tuple[int, int, str, str]]:
    try:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger, Doc
        seg = Segmenter()
        emb = NewsEmbedding()
        tagger = NewsNERTagger(emb)
        doc = Doc(text)
        doc.segment(seg)
        doc.tag_ner(tagger)
        label_map = {"PER": "ФИО", "ORG": "ОРГ"}
        result = []
        for span in doc.spans:
            if span.type not in label_map:
                continue
            value = text[span.start:span.stop]
            if span.type == "PER" and not _all_words_capitalized(value):
                continue
            result.append((span.start, span.stop, label_map[span.type], value))
        return result
    except Exception:
        return []


def _natasha_entities_per_line(text: str) -> list[tuple[int, int, str, str]]:
    try:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger, Doc
        seg = Segmenter()
        emb = NewsEmbedding()
        tagger = NewsNERTagger(emb)
    except Exception:
        return []

    result: list[tuple[int, int, str, str]] = []
    label_map = {"PER": "ФИО", "ORG": "ОРГ"}

    line_offset = 0
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if stripped and re.match(
            r'^[А-ЯЁ][а-яёА-ЯЁ\-]+(?:\s+[А-ЯЁ][а-яёА-ЯЁ\-]+){1,3}$',
            stripped
        ):
            if not _all_words_capitalized(stripped):
                line_offset += len(raw_line) + 1
                continue
            if any(_is_geo_word(w) for w in stripped.split()):
                line_offset += len(raw_line) + 1
                continue
            probe = _NER_PREFIX + stripped
            try:
                doc = Doc(probe)
                doc.segment(seg)
                doc.tag_ner(tagger)
                for span in doc.spans:
                    if span.type not in label_map:
                        continue
                    if span.start < _NER_PREFIX_LEN:
                        continue
                    orig_start = line_offset + (span.start - _NER_PREFIX_LEN)
                    orig_end   = line_offset + (span.stop  - _NER_PREFIX_LEN)
                    value = text[orig_start:orig_end]
                    result.append((orig_start, orig_end, label_map[span.type], value))
            except Exception:
                pass

        line_offset += len(raw_line) + 1

    return result


def _presidio_entities(text: str) -> list[tuple[int, int, str, str]]:
    try:
        from presidio_analyzer.predefined_recognizers import (
            EmailRecognizer, IpRecognizer, PhoneRecognizer,
        )
        label_map = {"EMAIL_ADDRESS": "EMAIL", "IP_ADDRESS": "IP", "PHONE_NUMBER": "ТЕЛЕФОН"}
        recognizers = [EmailRecognizer(), IpRecognizer(), PhoneRecognizer()]
        result = []
        for rec in recognizers:
            hits = rec.analyze(text=text, entities=rec.supported_entities, nlp_artifacts=None)
            for hit in hits:
                label = label_map.get(hit.entity_type, hit.entity_type)
                result.append((hit.start, hit.end, label, text[hit.start:hit.end]))
        return result
    except Exception:
        return []


def _postfilter_spans(
    spans: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """Фильтрация ложных срабатываний Natasha.

    Отклоняет:
    - PER/ФИО — если все токены нарицательные (словарь + pymorphy2)
    - ORG/ОРГ — если все токены присутствуют в _ORG_COMMON_WORDS
    """
    try:
        from core.detector_patch import natasha_postfilter
        spans = natasha_postfilter(spans)
    except ImportError:
        pass

    # Дополнительный фильтр для ОРГ: однословные нарицательные
    filtered: list[tuple[int, int, str, str]] = []
    for span in spans:
        label = span[2]
        value = span[3]
        if label in ("ОРГ", "ORG", "organization"):
            tokens = value.split()
            if all(_is_org_common_word(t) for t in tokens):
                import logging as _log
                _log.getLogger(__name__).info(
                    "Postfilter: отклонён ORG '%s' — все токены нарицательные", value
                )
                continue
        filtered.append(span)
    return filtered


def _merge_spans(
    spans: list[tuple[int, int, str, str]]
) -> list[tuple[int, int, str, str]]:
    spans = sorted(spans, key=lambda s: (s[0], -(s[1] - s[0])))
    merged: list[tuple[int, int, str, str]] = []
    last_end = -1
    for span in spans:
        if span[0] >= last_end:
            merged.append(span)
            last_end = span[1]
    return merged


def detect_entities(
    text: str,
    use_natasha: bool = True,
    use_presidio: bool = True,
    use_regex: bool = True,
    labels: set[str] | None = None,
) -> list[tuple[int, int, str, str]]:
    """Detect all PII entities in text (base pipeline: Natasha + Presidio + regex).

    Ollama/GLiNER are NOT called here — they are triggered manually via the UI
    and merged into the entity list before anonymize() is called.
    """
    spans: list[tuple[int, int, str, str]] = []
    if use_regex:
        spans += _regex_entities(text)
    if use_natasha:
        spans += _natasha_entities(text)
        spans += _natasha_entities_per_line(text)
    if use_presidio:
        spans += _presidio_entities(text)
    spans = _expand_org_spans(text, spans)
    # Постфильтр: удалить нарицательные ФИО/ОРГ до merge, чтобы не занимать span
    spans = _postfilter_spans(spans)
    spans = _merge_spans(spans)
    if labels:
        spans = [s for s in spans if s[2] in labels]
    return spans


def anonymize(
    text: str,
    enabled_labels: set[str] | None = None,
    predetected_entities: list[tuple[int, int, str, str]] | None = None,
) -> tuple[str, dict[str, dict[str, str]]]:
    """Replace PII entities with placeholders.

    Args:
        text: original text.
        enabled_labels: if set, only entities with these labels are masked.
        predetected_entities: if provided, detection is SKIPPED and this list
            is used directly. Pass session_state[_ENTITIES] when Ollama was
            already run manually — avoids redundant re-detection.
    """
    if predetected_entities is not None:
        spans = list(predetected_entities)
        if enabled_labels:
            spans = [s for s in spans if s[2] in enabled_labels]
        spans = _merge_spans(spans)
    else:
        spans = detect_entities(text, labels=enabled_labels)

    counters: dict[str, int] = {}
    mapping: dict[str, dict[str, str]] = {}
    value_cache: dict[str, str] = {}
    replacements: list[tuple[int, int, str]] = []
    for start, end, label, value in spans:
        if value in value_cache:
            placeholder = value_cache[value]
        else:
            counters[label] = counters.get(label, 0) + 1
            placeholder = f'[{label}_{counters[label]}]'
            value_cache[value] = placeholder
            mapping.setdefault(label, {})[placeholder] = value
        replacements.append((start, end, placeholder))
    result = text
    for start, end, placeholder in sorted(replacements, key=lambda x: -x[0]):
        result = result[:start] + placeholder + result[end:]
    return result, mapping


def anonymize_extra_terms(
    text: str,
    terms: list[str],
    mapping: dict[str, dict[str, str]],
) -> tuple[str, dict[str, dict[str, str]]]:
    counter = len(mapping.get("СКРЫТО", {}))
    value_cache: dict[str, str] = {}
    for term in terms:
        term = term.strip()
        if not term:
            continue
        term_lower = term.lower()
        if term_lower in value_cache:
            placeholder = value_cache[term_lower]
        else:
            counter += 1
            placeholder = f'[СКРЫТО_{counter}]'
            value_cache[term_lower] = placeholder
            mapping.setdefault("СКРЫТО", {})[placeholder] = term
        text = re.sub(re.escape(term), placeholder, text, flags=re.IGNORECASE)
    return text, mapping


def restore(anonymized_text: str, mapping: dict[str, Any]) -> str:
    result = anonymized_text
    for label_dict in mapping.values():
        for placeholder, original in label_dict.items():
            result = result.replace(placeholder, original)
    return result


def mapping_to_json(mapping: dict[str, dict[str, str]]) -> bytes:
    return json.dumps(mapping, ensure_ascii=False, indent=2).encode("utf-8")


def mapping_from_json(data: bytes | str) -> dict[str, Any]:
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(data)
