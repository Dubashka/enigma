"""MD anonymization view — Step 1: upload (any format), Step 2: review, Step 3: download.

Поддерживаемые форматы на входе: .md, .txt, .pdf, .docx, .doc, .pptx, .odt
Формат на выходе: .md (Markdown)

PDF-скан → Tesseract OCR, остальные → markitdown.
Ollama AI NER — доступна при запущенном Ollama (localhost:11434).
"""
from __future__ import annotations

import threading
import traceback

import streamlit as st
from ui.step_indicator import render_steps, STEPS_MD_MASK

_STAGE         = "md_mask_stage"
_STAGE_UPLOAD  = "upload"
_STAGE_REVIEW  = "review"
_STAGE_RESULT  = "result"

_FILE_NAME   = "md_mask_file_name"
_FILE_TEXT   = "md_mask_file_text"
_ANON_TEXT   = "md_mask_anon_text"
_MAPPING     = "md_mask_mapping"
_ENTITIES    = "md_mask_entities"
_AI_DONE     = "md_mask_ai_done"
_AI_DELTA    = "md_mask_ai_delta"
_AI_REMOVED  = "md_mask_ai_removed"
_CONV_WARN   = "md_mask_conv_warn"
# Ошибка Ollama сохраняется в session_state чтобы пережить st.rerun()
_AI_ERROR    = "md_mask_ai_error"       # str | None — текст ошибки
_AI_ERROR_KIND = "md_mask_ai_error_kind"  # "timeout" | "unavailable" | "parse" | "unexpected"

_OLLAMA_ENABLED = True

_ACCEPTED_TYPES = ["md", "txt", "pdf", "docx", "doc", "pptx", "odt"]

_TYPE_LABELS = {
    "md":   "Markdown",
    "txt":  "Текст (TXT)",
    "pdf":  "PDF документ",
    "docx": "Word документ",
    "doc":  "Word документ (старый формат)",
    "pptx": "PowerPoint презентация",
    "odt":  "OpenDocument текст",
}

_FILE_EMOJI = {
    "md":   "📄", "txt": "📄",
    "pdf":  "📑",
    "docx": "📝", "doc": "📝",
    "pptx": "📊",
    "odt":  "📄",
}

ALL_LABELS = ["ФИО", "ОРГ", "EMAIL", "ТЕЛЕФОН", "IP", "ДОГОВОР", "СУММА", "ДАТА", "АДРЕС",
              "ПАСПОРТ", "СНИЛС", "ИНН", "КПП"]

LABEL_DESCRIPTIONS = {
    "ФИО":     "Имена и фамилии людей",
    "ОРГ":     "Названия организаций",
    "EMAIL":   "Адреса электронной почты",
    "ТЕЛЕФОН": "Номера телефонов",
    "IP":      "IP-адреса",
    "ДОГОВОР": "Номера договоров и документов",
    "СУММА":   "Денежные суммы",
    "ДАТА":    "Даты",
    "АДРЕС":   "Физические адреса",
    "ПАСПОРТ": "Паспортные данные (серия + номер)",
    "СНИЛС":   "СНИЛС",
    "ИНН":     "ИНН физического или юридического лица",
    "КПП":     "КПП организации",
}

_LANG_OPTIONS = {
    "Русский + Английский": "rus+eng",
    "Только русский":       "rus",
    "Только английский":    "eng",
}

# Таймаут должен совпадать с _TIMEOUT в core/ai_ner.py
_OLLAMA_TIMEOUT_SEC = 300


def render() -> None:
    st.header("Маскирование документов")
    stage = st.session_state.get(_STAGE, _STAGE_UPLOAD)
    if stage == _STAGE_UPLOAD:
        _render_upload()
    elif stage == _STAGE_REVIEW:
        _render_review()
    elif stage == _STAGE_RESULT:
        _render_result()


# ---------------------------------------------------------------------------
# Шаг 1 — загрузка и конвертация
# ---------------------------------------------------------------------------

def _render_upload() -> None:
    render_steps(current=1, steps=STEPS_MD_MASK)
    st.subheader("Загрузите документ")
    st.caption(
        "Поддерживаются: "
        + ", ".join(f"**{ext.upper()}**" for ext in _ACCEPTED_TYPES)
        + " — результат маскирования всегда в формате **.md**"
    )

    uploaded = st.file_uploader(" ", type=_ACCEPTED_TYPES, key="md_mask_uploader")

    if uploaded is None:
        return

    ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
    is_pdf = ext == "pdf"

    force_ocr = False
    ocr_lang  = "rus+eng"
    if is_pdf:
        st.markdown("---")
        st.markdown("**Параметры PDF**")
        force_ocr = st.checkbox(
            "Сканированный PDF (использовать Tesseract OCR)",
            value=False,
            help=(
                "Включите, если PDF является сканом без выделяемого текста. "
                "Иначе текст извлекается быстро через markitdown без запуска OCR."
            ),
        )
        if force_ocr:
            lang_label = st.selectbox(
                "Язык распознавания",
                options=list(_LANG_OPTIONS.keys()),
                index=0,
            )
            ocr_lang = _LANG_OPTIONS[lang_label]
            st.info("⏰ OCR может занять несколько минут на большой документ.")

    st.markdown("---")
    if st.button("Загрузить и анализировать", type="primary", use_container_width=True):
        file_bytes = uploaded.read()

        needs_conversion = ext not in ("md", "txt")
        if needs_conversion:
            label = _TYPE_LABELS.get(ext, ext.upper())
            with st.spinner(f"Конвертируем {label} в Markdown…"):
                try:
                    from core.converter import file_to_markdown
                    text, conv_warning = file_to_markdown(
                        file_bytes,
                        uploaded.name,
                        ocr_lang=ocr_lang,
                        force_ocr=force_ocr,
                    )
                except RuntimeError as err:
                    st.error(f"❌ Не удалось конвертировать файл: {err}")
                    return
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            conv_warning = None

        if not text.strip():
            st.error(
                "Документ не содержит текста или не удалось его извлечь. "
                "Попробуйте включить OCR (если PDF-скан) или проверьте файл."
            )
            return

        with st.spinner("Ищем чувствительные данные…"):
            from core.md_anonymizer import detect_entities
            entities = detect_entities(text)

        st.session_state[_FILE_NAME] = uploaded.name
        st.session_state[_FILE_TEXT] = text
        st.session_state[_ENTITIES]  = entities
        st.session_state[_AI_DONE]   = False
        st.session_state[_AI_DELTA]  = 0
        st.session_state[_AI_REMOVED] = 0
        st.session_state[_CONV_WARN] = conv_warning
        st.session_state.pop(_AI_ERROR, None)
        st.session_state.pop(_AI_ERROR_KIND, None)
        st.session_state[_STAGE]     = _STAGE_REVIEW
        st.rerun()


# ---------------------------------------------------------------------------
# Шаг 2 — просмотр и редактирование сущностей
# ---------------------------------------------------------------------------

def _render_review() -> None:
    render_steps(current=2, steps=STEPS_MD_MASK)
    text      = st.session_state[_FILE_TEXT]
    entities  = st.session_state[_ENTITIES]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    conv_warn = st.session_state.get(_CONV_WARN)

    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in ("md", "txt"):
        emoji = _FILE_EMOJI.get(ext, "📄")
        label = _TYPE_LABELS.get(ext, ext.upper())
        st.info(
            f"{emoji} Файл **{file_name}** ({label}) был сконвертирован в Markdown "
            "перед анализом. Результат маскирования будет в формате **.md**.",
            icon="ℹ️",
        )
    if conv_warn:
        st.warning(f"⚠️ {conv_warn}")

    st.subheader(f"Найденные чувствительные данные: {file_name}")

    if _OLLAMA_ENABLED:
        _render_ollama_block(text)
    else:
        with st.expander("🚧 Уточнить через Ollama (в разработке)", expanded=False):
            st.info(
                "🛠️ Эта функция ещё в разработке и будет доступна в ближайшем обновлении.\n\n"
                "Позволит запустить локальную LLM-модель (Ollama) для поиска дополнительных сущностей, "
                "которые не были найдены базовым сканированием (Natasha + Presidio + regex).",
                icon="ℹ️",
            )
            st.button(
                "🤖 Уточнить через Ollama",
                disabled=True,
                use_container_width=True,
                help="Функция в разработке — недоступна",
            )

    st.markdown("---")

    by_label: dict[str, list[str]] = {}
    for _, _, label, value in entities:
        by_label.setdefault(label, [])
        if value not in by_label[label]:
            by_label[label].append(value)

    if not by_label:
        st.info("Чувствительные данные в файле не обнаружены. Можно скачать файл без изменений.")
    else:
        st.markdown("Выберите типы данных для маскирования:")
        for label in ALL_LABELS:
            if label not in by_label:
                continue
            values = by_label[label]
            col_cb, col_vals = st.columns([0.25, 0.75])
            with col_cb:
                st.checkbox(
                    f"**{label}** ({len(values)} шт.)",
                    value=True,
                    key=f"md_label_{label}",
                )
            with col_vals:
                preview = ",  ".join(f"`{v}`" for v in values[:5])
                if len(values) > 5:
                    preview += f"  _...ещё {len(values) - 5}_"
                st.markdown(
                    f"<span style='color:#666;font-size:0.85em'>{preview}</span>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")
    st.markdown("Дополнительные слова и фразы для маскировки")
    st.text_area(
        "Введите через запятую",
        key="md_extra_terms",
        height=80,
        placeholder="Проект Альфа, сервер БД, филиал №3",
    )

    col_back, col_anon = st.columns([1, 1])
    with col_back:
        if st.button("Назад", use_container_width=True):
            _reset()
            st.rerun()
    with col_anon:
        if st.button("Маскировать", type="primary", use_container_width=True):
            enabled = {l for l in ALL_LABELS if st.session_state.get(f"md_label_{l}", False)}
            if not enabled and not st.session_state.get("md_extra_terms", "").strip():
                st.warning("Выберите хотя бы один тип данных или введите дополнительные слова")
            else:
                from core.md_anonymizer import anonymize, anonymize_extra_terms
                anon_text, mapping = anonymize(
                    text,
                    enabled_labels=enabled if enabled else None,
                    predetected_entities=st.session_state.get(_ENTITIES),
                )
                raw_extra = st.session_state.get("md_extra_terms", "")
                extra_terms = [t.strip() for t in raw_extra.split(",") if t.strip()]
                if extra_terms:
                    anon_text, mapping = anonymize_extra_terms(anon_text, extra_terms, mapping)

                st.session_state[_ANON_TEXT] = anon_text
                st.session_state[_MAPPING]   = mapping
                st.session_state[_STAGE]     = _STAGE_RESULT
                st.rerun()


# ---------------------------------------------------------------------------
# Ollama block
# ---------------------------------------------------------------------------

def _render_ollama_block(text: str) -> None:
    ai_done      = st.session_state.get(_AI_DONE, False)
    ai_delta     = st.session_state.get(_AI_DELTA, 0)
    ai_removed   = st.session_state.get(_AI_REMOVED, 0)
    ai_error     = st.session_state.get(_AI_ERROR)
    ai_error_kind = st.session_state.get(_AI_ERROR_KIND)

    st.markdown("---")
    ai_col1, ai_col2 = st.columns([2, 3])
    with ai_col1:
        btn_label = "✅ Ollama уже применена" if ai_done else "🤖 Уточнить через Ollama"
        clicked = st.button(
            btn_label,
            disabled=ai_done,
            use_container_width=True,
            key="btn_ollama",
            help=(
                "Запустить локальную LLM (Ollama) для проверки базового списка "
                "и поиска новых сущностей. Ollama уберёт OCR-мусор и ложные срабатывания, "
                "а также найдёт то, что пропустил базовый сканер. "
                "Требует запущенного Ollama на localhost:11434."
            ),
        )
    with ai_col2:
        if ai_done:
            parts = []
            if ai_delta > 0:
                parts.append(f"добавлено **+{ai_delta}**")
            elif ai_delta == 0:
                parts.append("новых не найдено")
            if ai_removed > 0:
                parts.append(f"удалено мусора **−{ai_removed}**")
            msg = "Ollama завершила анализ: " + ", ".join(parts) + ". Список обновлён."
            st.success(msg, icon="✅")
        elif ai_error:
            # Ошибка пережила rerun — показываем её
            _show_ollama_error(ai_error_kind, ai_error)
        else:
            st.info(
                "Базовое сканирование выполнено (Natasha + Presidio + regex). "
                "Нажмите кнопку слева, чтобы запустить Ollama — она проверит список "
                "и уберёт ложные срабатывания.",
                icon="ℹ️",
            )

    if clicked and not ai_done:
        # Сбрасываем предыдущую ошибку перед новой попыткой
        st.session_state.pop(_AI_ERROR, None)
        st.session_state.pop(_AI_ERROR_KIND, None)
        _run_ollama_and_merge(text)
        st.rerun()

    st.markdown("---")


def _show_ollama_error(kind: str | None, message: str) -> None:
    """Единая точка отображения ошибок Ollama."""
    if kind == "timeout":
        st.error(
            f"**⏰ Ollama не успела ответить за {_OLLAMA_TIMEOUT_SEC} сек.**\n\n"
            f"{message}\n\n"
            "Возможные причины:\n"
            "• Модель ещё загружается — попробуйте снова через минуту.\n"
            "• Документ слишком большой — разбейте на части.\n"
            "• Не хватает RAM/VRAM.\n\n"
            "Базовый список сущностей сохранён — можно продолжить без Ollama.",
            icon="⏰",
        )
    elif kind == "unavailable":
        st.error(
            f"**🔴 Ollama недоступна.**\n\n"
            f"{message}\n\n"
            "Убедитесь что Ollama запущена: `ollama serve`\n\n"
            "Базовый список сущностей сохранён — можно продолжить без Ollama.",
            icon="🔴",
        )
    elif kind == "parse":
        st.error(
            f"**🟠 Ollama вернула некорректный ответ (не удалось разобрать JSON).**\n\n"
            f"{message}\n\n"
            "Попробуйте снова или используйте другую модель.",
            icon="🟠",
        )
    else:
        st.error(
            f"**❌ Неожиданная ошибка Ollama.**\n\n"
            f"{message}",
            icon="❌",
        )


# ---------------------------------------------------------------------------
# Ollama helper — запуск через thread.join(timeout) без блокировки UI
# ---------------------------------------------------------------------------

def _run_ollama_and_merge(text: str) -> None:
    """
    Запускает Ollama в фоновом потоке с передачей базового списка.
    Ollama возвращает confirmed / false_positives / new.
    false_positives удаляются из базового списка, new — добавляются.

    Все ошибки сохраняются в session_state (_AI_ERROR / _AI_ERROR_KIND)
    чтобы пережить вызов st.rerun() в _render_ollama_block.
    """
    from core.ai_ner import (
        AINer, merge_entity_lists,
        OllamaUnavailableError, OllamaTimeoutError, OllamaParseError,
    )

    base_entities = st.session_state.get(_ENTITIES, [])
    base_count    = len(base_entities)

    result_box: dict = {"new_entities": None, "fp_indices": None, "error": None}

    def _worker() -> None:
        try:
            ner = AINer(mode="ollama")
            new_entities, fp_indices = ner.extract(text, base_entities=base_entities)
            result_box["new_entities"] = new_entities
            result_box["fp_indices"]   = fp_indices
        except Exception as exc:  # noqa: BLE001
            result_box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    spinner_msg = (
        f"🤖 Ollama анализирует текст… (макс. {_OLLAMA_TIMEOUT_SEC} сек)  \n"
        "Не закрывайте страницу."
    )
    with st.spinner(spinner_msg):
        thread.join(timeout=_OLLAMA_TIMEOUT_SEC)

    # --- Поток завис (thread.join вернул управление по таймауту) ---
    if thread.is_alive():
        st.session_state[_AI_ERROR] = (
            f"Поток Ollama не завершился за {_OLLAMA_TIMEOUT_SEC} сек. "
            "Модель может быть перегружена или документ слишком большой."
        )
        st.session_state[_AI_ERROR_KIND] = "timeout"
        return

    # --- Ошибка внутри потока ---
    err = result_box["error"]
    if err is not None:
        err_text = str(err)
        if isinstance(err, OllamaTimeoutError):
            st.session_state[_AI_ERROR_KIND] = "timeout"
        elif isinstance(err, OllamaUnavailableError):
            st.session_state[_AI_ERROR_KIND] = "unavailable"
        elif isinstance(err, OllamaParseError):
            st.session_state[_AI_ERROR_KIND] = "parse"
            # Для ошибок парсинга добавляем трейсбэк — помогает при отладке
            err_text = f"{err}\n\n```\n{traceback.format_exc()}\n```"
        else:
            st.session_state[_AI_ERROR_KIND] = "unexpected"
            err_text = f"{err}\n\n```\n{traceback.format_exc()}\n```"
        st.session_state[_AI_ERROR] = err_text
        return

    # --- Успех ---
    new_entities = result_box["new_entities"] or []
    fp_indices   = result_box["fp_indices"] or set()

    merged = merge_entity_lists(
        base_entities,
        new_entities,
        exclude_indices=fp_indices,
    )

    st.session_state[_ENTITIES]   = merged
    st.session_state[_AI_DONE]    = True
    st.session_state[_AI_DELTA]   = len(merged) - (base_count - len(fp_indices))
    st.session_state[_AI_REMOVED] = len(fp_indices)
    # Убираем ошибку если предыдущий запуск был неудачным
    st.session_state.pop(_AI_ERROR, None)
    st.session_state.pop(_AI_ERROR_KIND, None)


# ---------------------------------------------------------------------------
# Шаг 3 — результат
# ---------------------------------------------------------------------------

def _render_result() -> None:
    render_steps(current=3, steps=STEPS_MD_MASK)
    anon_text = st.session_state[_ANON_TEXT]
    mapping   = st.session_state[_MAPPING]
    file_name = st.session_state.get(_FILE_NAME, "файл")
    base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    st.subheader("Результат маскирования")

    cols = st.columns(max(len(mapping), 1))
    for i, (label, items) in enumerate(mapping.items()):
        cols[i % len(cols)].metric(label, len(items))

    st.markdown("**Превью (первые 1000 символов)**")
    st.code(anon_text[:1000] + ("…" if len(anon_text) > 1000 else ""), language="markdown")

    st.warning("⚠️ Не забудьте скачать маппинг (.json) для дальнейшего демаскирования")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Маскированный .md",
            data=anon_text.encode("utf-8"),
            file_name=f"{base}_anon.md",
            mime="text/markdown",
            use_container_width=True,
            type="primary",
        )
    with col2:
        from core.md_anonymizer import mapping_to_json
        st.download_button(
            label="Маппинг (.json)",
            data=mapping_to_json(mapping),
            file_name=f"{base}_mapping.json",
            mime="application/json",
            use_container_width=True,
            type="primary",
        )

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("Назад к выбору сущностей", use_container_width=True):
            for k in [_ANON_TEXT, _MAPPING]:
                st.session_state.pop(k, None)
            st.session_state[_STAGE] = _STAGE_REVIEW
            st.rerun()
    with col_reset:
        if st.button("Сбросить", use_container_width=True):
            _reset()
            st.rerun()


def _reset() -> None:
    for key in [_STAGE, _FILE_NAME, _FILE_TEXT, _ANON_TEXT, _MAPPING,
                _ENTITIES, _AI_DONE, _AI_DELTA, _AI_REMOVED, _CONV_WARN,
                _AI_ERROR, _AI_ERROR_KIND]:
        st.session_state.pop(key, None)
    for label in ALL_LABELS:
        st.session_state.pop(f"md_label_{label}", None)
    st.session_state.pop("md_extra_terms", None)
