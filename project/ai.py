# -*- coding: utf-8 -*-
"""
Интеграция с OpenAI API и демо-режим без ключа (для хакатона).
Все ответы ориентированы на ремесленников / малый бизнес / ECO.
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

# .env рядом с этим файлом — ключ подхватится при любом способе запуска
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_PKG_DIR, ".env"))

# Системный промпт для чата-ассистента
HUB_SYSTEM_PROMPT = """Ты — AI-ассистент платформы «SpiralHubAI» для ремесленников,
самозанятых и малого бизнеса в России и СНГ. Помогаешь с:
описаниями товаров, ценообразованием, идеями продуктов, анализом бизнеса,
ростом продаж и экологичными (ESG/eco) рекомендациями.
Отвечай кратко, по делу, дружелюбно. Если данных мало — уточни один вопрос."""


def _resolved_model(explicit: Optional[str] = None) -> str:
    """Модель из аргумента, иначе OPENAI_MODEL из .env, иначе gpt-4o-mini."""
    if explicit and explicit.strip():
        return explicit.strip()
    m = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    return m or "gpt-4o-mini"


def _vision_model() -> str:
    """Модель с поддержкой изображений (Vision). По умолчанию gpt-4o-mini."""
    m = os.environ.get("OPENAI_VISION_MODEL", "").strip()
    return m or "gpt-4o-mini"


# Промпт для распознавания товара по фото и вариантов описания
_IMAGE_ANALYSIS_SCHEMA = (
    "Ответь ТОЛЬКО JSON (без markdown и без пояснений снаружи JSON):\n"
    '{"detected":"кратко что на фото по-русски (1 предложение)",'
    '"title":"предлагаемое название товара для карточки, до 90 символов",'
    '"category":"одно из: eco, handmade, agro, bio",'
    '"descriptions":["вариант 1: продающее описание 2-4 предложения",'
    '"вариант 2: другой тон/акцент","вариант 3: короче, для соцсетей или карточки"]}'
)


def _client() -> Optional[OpenAI]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    return OpenAI(api_key=key)


def is_demo_mode() -> bool:
    return _client() is None


def chat_completion(messages: list[dict[str, str]], model: Optional[str] = None) -> str:
    """
    Универсальный чат. messages: [{"role":"user"|"assistant"|"system","content":"..."}]
    """
    client = _client()
    if not client:
        return _demo_chat_reply(messages)

    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "system", "content": HUB_SYSTEM_PROMPT}, *messages],
            temperature=0.7,
            max_tokens=1024,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[Ошибка API: {e}] Переключитесь на демо или проверьте ключ."


def generate_product_description(
    title: str, category: str, hints: str = "", model: Optional[str] = None
) -> str:
    """Генерация описания товара для карточки маркетплейса."""
    user = (
        f"Название: {title}\nКатегория: {category}\n"
        f"Доп. пожелания продавца: {hints or 'нет'}\n\n"
        "Напиши продающее описание 3–5 предложений для маркетплейса ремесленников."
    )
    client = _client()
    if not client:
        return (
            f"«{title}» — авторская работа в категории «{category}». "
            "Натуральные материалы, внимание к деталям, удобная доставка. "
            "Идеально для тех, кто ценит handmade и осознанное потребление. "
            "(Демо: задайте OPENAI_API_KEY в .env для полной генерации.)"
        )
    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.8,
            max_tokens=400,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Не удалось сгенерировать: {e}"


def analyze_product_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict[str, Any]:
    """
    Vision: определить товар по фото и предложить название, категорию и 3 варианта описания.
    Возвращает dict: detected, title, category, descriptions (list[str]).
    """
    if not image_bytes or len(image_bytes) < 32:
        return _demo_image_analysis("Пустой или слишком маленький файл.")

    client = _client()
    if not client:
        return _demo_image_analysis(None)

    mime = (mime_type or "image/jpeg").split(";")[0].strip().lower()
    if mime not in ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"):
        mime = "image/jpeg"
    if mime == "image/jpg":
        mime = "image/jpeg"

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    user_text = (
        "Ты помощник маркетплейса SpiralHubAI для ремесленников и малого бизнеса. "
        "Посмотри на фото товара. Определи, что это (продукт питания, изделие ручной работы, "
        "растение, декор и т.д.). Предложи уместную категорию из списка и три разных по стилю описания.\n\n"
        + _IMAGE_ANALYSIS_SCHEMA
    )

    mdl = _vision_model()
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "low"},
                        },
                    ],
                },
            ],
            temperature=0.65,
            max_tokens=900,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_image_analysis_json(raw)
    except Exception as e:
        return {
            "detected": f"Ошибка Vision API: {e}",
            "title": "Товар по фото",
            "category": "handmade",
            "descriptions": [
                "Не удалось разобрать ответ модели. Опишите товар вручную или повторите попытку.",
                "Проверьте формат изображения (PNG, JPG, WEBP) и ключ OPENAI_API_KEY.",
                "Убедитесь, что в .env задана модель с Vision, например OPENAI_VISION_MODEL=gpt-4o-mini.",
            ],
            "error": str(e),
        }


def _parse_image_analysis_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    allowed_cat = {"eco", "handmade", "agro", "bio"}
    try:
        data = json.loads(text)
        detected = str(data.get("detected", "")).strip() or "Товар на фото"
        title = str(data.get("title", "")).strip()[:200] or "Новый товар"
        cat = str(data.get("category", "handmade")).lower().strip()
        if cat not in allowed_cat:
            cat = "handmade"
        descs = data.get("descriptions")
        if not isinstance(descs, list):
            descs = []
        out_descs = [str(x).strip() for x in descs if str(x).strip()][:3]
        while len(out_descs) < 3:
            out_descs.append(title + " — уточните детали вручную.")
        return {
            "detected": detected[:500],
            "title": title,
            "category": cat,
            "descriptions": out_descs[:3],
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "detected": "Не удалось разобрать JSON от модели.",
            "title": "Товар по фото",
            "category": "handmade",
            "descriptions": [text[:600] if text else "Пустой ответ.", "Вариант 2 уточните вручную.", "Вариант 3 уточните вручную."],
        }


def _demo_image_analysis(note: Optional[str]) -> dict[str, Any]:
    msg = note or (
        "Демо-режим: задайте OPENAI_API_KEY в .env — модель посмотрит фото и заполнит поля."
    )
    return {
        "detected": msg,
        "title": "Авторский товар (демо)",
        "category": "handmade",
        "demo": True,
        "descriptions": [
            "Демо-вариант 1: уникальное изделие ручной работы, внимание к деталям и натуральные материалы. "
            "Подойдёт для дома или в подарок.",
            "Демо-вариант 2: акцент на экологичность и локальное производство. Доставка обсуждается с продавцом.",
            "Демо-вариант 3: коротко: качество, стиль, бережная упаковка. Напишите размеры и уход вручную при публикации.",
        ],
        "demo": True,
    }


def eco_recommendations_for_product(title: str, description: str) -> str:
    """Короткие AI-рекомендации по экологичности упаковки и процесса."""
    user = (
        f"Товар: {title}\nОписание: {description[:800]}\n\n"
        "Дай 3–5 bullet-рекомендаций: упаковка, логистика, материалы, сертификации."
    )
    client = _client()
    if not client:
        return (
            "• Используйте переработанную или крафт-упаковку.\n"
            "• Укажите происхождение сырья (локальное предпочтительно).\n"
            "• Рассмотрите компостируемые этикетки.\n"
            "• Минимизируйте воздушные отправления — группируйте заказы.\n"
            "(Демо-режим: добавьте OPENAI_API_KEY в .env.)"
        )
    mdl = _resolved_model(None)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.6,
            max_tokens=500,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Ошибка: {e}"


def assess_credit_llm(
    monthly_income: float,
    sales_count_30d: int,
    business_description: str,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """
    AI-оценка заявки: JSON с risk (low|medium|high), approval_probability (0-100), summary.
    """
    user = json.dumps(
        {
            "monthly_income": monthly_income,
            "sales_count_30d": sales_count_30d,
            "business_description": business_description[:2000],
        },
        ensure_ascii=False,
    )
    schema_hint = (
        'Ответь ТОЛЬКО JSON: {"risk":"low|medium|high",'
        '"approval_probability": число 0-100, "summary": "краткое обоснование на русском"}'
    )
    client = _client()
    if not client:
        return _demo_credit_assessment(monthly_income, sales_count_30d, business_description)

    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT + " " + schema_hint},
                {"role": "user", "content": "Оцени микрокредит для малого бизнеса/ремесленника:\n" + user},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        text = (resp.choices[0].message.content or "").strip()
        return _parse_credit_json(text)
    except Exception as e:
        return {
            "risk": "medium",
            "approval_probability": 50,
            "summary": f"Ошибка LLM: {e}. Показана усреднённая оценка.",
        }


def _parse_credit_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        risk = str(data.get("risk", "medium")).lower()
        if risk not in ("low", "medium", "high"):
            risk = "medium"
        prob = int(data.get("approval_probability", 55))
        prob = max(0, min(100, prob))
        summary = str(data.get("summary", ""))[:2000]
        return {"risk": risk, "approval_probability": prob, "summary": summary}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "risk": "medium",
            "approval_probability": 55,
            "summary": "Не удалось разобрать ответ модели; примите решение вручную.",
        }


def narrate_credit_assessment(
    *,
    applicant_name: str,
    requested_amount: float,
    monthly_income: float,
    sales_count_30d: int,
    experience_months: int,
    business_category: str,
    business_description: str,
    risk: str,
    approval_probability: int,
    recommended_amount: float,
    sustainable_business: bool,
    decision_recommendation: str,
    model: Optional[str] = None,
) -> dict[str, str]:
    """
    Пояснение и советы по уже рассчитанной заявке (цифры из формулы не менять в тексте).

    Возвращает: summary, tips_improve (как повысить шанс), tips_grow (развитие бизнеса).
    """
    payload = {
        "applicant_name": applicant_name,
        "requested_amount": requested_amount,
        "monthly_income": monthly_income,
        "sales_count_30d": sales_count_30d,
        "experience_months": experience_months,
        "business_category": business_category,
        "business_description": (business_description or "")[:2500],
        "risk": risk,
        "approval_probability": approval_probability,
        "recommended_amount": recommended_amount,
        "sustainable_business": sustainable_business,
        "decision_recommendation": decision_recommendation,
    }
    schema = (
        'Ответь ТОЛЬКО JSON без markdown: {"summary":"2-4 предложения: объясни оценку простым языком",'
        '"tips_improve":"маркированный текст или абзац: как повысить шанс одобрения",'
        '"tips_grow":"как развивать бизнес дальше"}'
    )
    user = (
        "Ты финтех-аналитик микрокредитов для ремесленников и самозанятых (SpiralHubAI).\n"
        "Ниже уже рассчитаны показатели системой — в summary обязательно используй ТЕ ЖЕ числа "
        f"(вероятность {approval_probability}%, риск {risk}, рекомендуемая сумма {recommended_amount:,.0f} ₸), "
        "не выдумывай другие цифры.\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\n"
        + schema
    )
    client = _client()
    if not client:
        return _demo_narrate_credit(payload)

    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.45,
            max_tokens=700,
        )
        text = (resp.choices[0].message.content or "").strip()
        return _parse_narrate_credit_json(text, payload)
    except Exception as e:
        return _demo_narrate_credit(payload, error=str(e))


def _parse_narrate_credit_json(text: str, payload: dict[str, Any]) -> dict[str, str]:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        summary = str(data.get("summary", "")).strip() or _demo_narrate_credit(payload)["summary"]
        tips_improve = str(data.get("tips_improve", "")).strip() or "Уточните объём продаж и стабильность дохода."
        tips_grow = str(data.get("tips_grow", "")).strip() or "Диверсифицируйте каналы сбыта и закрепите eco-практики в описании."
        return {
            "summary": summary[:3500],
            "tips_improve": tips_improve[:2500],
            "tips_grow": tips_grow[:2500],
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return _demo_narrate_credit(payload)


def _demo_narrate_credit(payload: dict[str, Any], error: str = "") -> dict[str, str]:
    name = (payload.get("applicant_name") or "Заявитель").strip()
    prob = int(payload.get("approval_probability") or 50)
    risk = str(payload.get("risk") or "medium")
    rec = float(payload.get("recommended_amount") or 0)
    dec = str(payload.get("decision_recommendation") or "improve")
    sust = bool(payload.get("sustainable_business"))
    err = f" ({error})" if error else ""
    summary = (
        f"{name}, демо-анализ{err}: при риске «{risk}» ориентировочная вероятность одобрения — {prob}%. "
        f"Рекомендуем ориентироваться на сумму до {rec:,.0f} ₸ с учётом вашего дохода и активности. "
    )
    if sust:
        summary += "Проект отмечен как устойчивый (eco/bio) — для программы ESG это плюс. "
    summary += (
        "С ключом OpenAI в .env пояснения будут персональнее; цифры остаются от внутренней формулы."
    )
    if dec == "approve":
        tips_i = (
            "• Подготовьте подтверждение дохода и оборотов за последние месяцы.\n"
            "• Сохраняйте или нарастите частоту продаж — это снижает риск в следующих заявках."
        )
    else:
        tips_i = (
            "• Уменьшите запрашиваемую сумму или увеличьте заявленный доход за счёт подтверждённых источников.\n"
            "• Нарастите продажи 30 дней и опишите стабильные каналы сбыта.\n"
            "• Если ниша eco — укажите сертификаты или практики (упаковка, сырьё)."
        )
    tips_g = (
        "• Вынесите eco-практики в профиль и карточки товаров.\n"
        "• Тестируйте малые партии и сбор предзаказов на платформе.\n"
        "• Закрепите повторные продажи (рассылка покупателям, комплекты)."
    )
    return {"summary": summary, "tips_improve": tips_i, "tips_grow": tips_g}


def _demo_chat_reply(messages: list[dict[str, str]]) -> str:
    last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last = (m.get("content") or "").lower()
            break
    if "цен" in last or "price" in last:
        return (
            "Демо-совет по цене: сравните с похожими лотами на площадке, "
            "заложите 20–30% на скидки/доставку. Для handmade цена = материалы + 2–4× время."
        )
    if "продаж" in last or "маркетинг" in last:
        return (
            "Демо: фото в естественном свете, история создания в описании, "
            "рассылка постоянным клиентам, коллаборации с локальными блогерами."
        )
    if "эко" in last or "eco" in last or "esg" in last:
        return (
            "Демо ECO: прозрачное происхождие сырья, минимальная упаковка, "
            "возможность возврата тары, сертификаты при наличии."
        )
    return (
        "Привет! Это демо-ответ SpiralHubAI: в файле project/.env не задан OPENAI_API_KEY. "
        "Вставьте ключ OpenAI и перезапустите приложение."
    )


def seller_dashboard_advice(
    display_name: str,
    role: str,
    products: list[dict[str, Any]],
    model: Optional[str] = None,
) -> dict[str, str]:
    """
    Блок «AI для профиля»: советы по продажам, ценам и идеи новых товаров.
    products — список словарей с ключами title, price, category, description (коротко).
    Возвращает ключи: sales_tips, pricing_tips, new_product_ideas.
    """
    name = (display_name or "Пользователь").strip()
    lines = [
        f"Имя/ник: {name}",
        f"Роль: {role}",
        "Каталог продавца (кратко):",
    ]
    if not products:
        lines.append("— пока нет опубликованных товаров в контексте.")
    else:
        for i, p in enumerate(products[:24], 1):
            lines.append(
                f"{i}. {p.get('title', '')} | {p.get('category', '')} | {p.get('price', '')} ₸ | "
                f"{str(p.get('description', ''))[:120]}"
            )
    user_block = "\n".join(lines)
    schema = (
        'Ответь ТОЛЬКО JSON (без markdown): {"sales_tips":"...",'
        '"pricing_tips":"...","new_product_ideas":"..."} '
        "Каждое поле — 2–4 коротких абзаца или маркированный текст на русском."
    )
    client = _client()
    if not client:
        if role != "seller" or not products:
            return {
                "sales_tips": (
                    "• Зарегистрируйтесь как продавец и добавьте первый товар с фото — так вас увидят в каталоге.\n"
                    "• Опишите историю мастерской: доверие растёт, когда покупатель понимает, кто стоит за изделием.\n"
                    "(Демо: OPENAI_API_KEY в project/.env — персональные советы по вашему каталогу.)"
                ),
                "pricing_tips": (
                    "• Когда появятся лоты, сравните цены с похожими в категории (eco / handmade / agro / bio).\n"
                    "• Заложите доставку и материалы; для handmade часто работает формула: сырьё + 2–3× время.\n"
                    "(Демо без API.)"
                ),
                "new_product_ideas": (
                    "• Наборы «товар + мини-курс» или limited series с нумерацией.\n"
                    "• Сезонные коллекции (праздники, урожай) — хорошо заходят в agro и handmade.\n"
                    "(Демо без API.)"
                ),
            }
        return {
            "sales_tips": (
                f"Демо для «{name}»: усильте фото (день, нейтральный фон), добавьте размеры и уход. "
                "В описании — для кого товар и срок изготовления. Расскажите историю в посте и в шапке витрины."
            ),
            "pricing_tips": (
                "Демо: проверьте медиану по категории; если продаёте редкий материал — обоснуйте цену в карточке. "
                "Пробуйте пакет «основной товар + мини-доп» для среднего чека."
            ),
            "new_product_ideas": (
                "Демо: мини-наборы к основному лоту, персонализация (гравировка/цвет), коллаборация с другим продавцом площадки. "
                "Добавьте OPENAI_API_KEY для идей под ваш реальный ассортимент."
            ),
        }

    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT + " " + schema},
                {
                    "role": "user",
                    "content": "Дай рекомендации мастеру/самозанятому для роста на маркетплейсе:\n" + user_block,
                },
            ],
            temperature=0.65,
            max_tokens=900,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_seller_advice_json(raw)
    except Exception as e:
        return {
            "sales_tips": f"Не удалось получить советы: {e}",
            "pricing_tips": "Повторите запрос позже или проверьте ключ API.",
            "new_product_ideas": "Пока опирайтесь на демо-тексты из режима без сети.",
        }


def _parse_seller_advice_json(text: str) -> dict[str, str]:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return {
            "sales_tips": str(data.get("sales_tips", "")).strip() or "—",
            "pricing_tips": str(data.get("pricing_tips", "")).strip() or "—",
            "new_product_ideas": str(data.get("new_product_ideas", "")).strip() or "—",
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "sales_tips": (text[:800] if text else "Пустой ответ модели."),
            "pricing_tips": "Уточните запрос или повторите.",
            "new_product_ideas": "См. блок выше или повторите генерацию.",
        }


def match_sellers_by_query(
    user_query: str,
    sellers_catalog: list[dict[str, Any]],
    model: Optional[str] = None,
) -> dict[str, Any]:
    """
    Подбор продавцов под запрос покупателя.
    sellers_catalog: id, name, bio, categories, product_sample, eco_percent.
    Возвращает ranked_ids (лучшие первые) и explanation.
    """
    q = (user_query or "").strip()
    if not sellers_catalog:
        return {"ranked_ids": [], "explanation": "Нет продавцов с активной витриной."}
    client = _client()
    if not client:
        return _demo_match_sellers(q, sellers_catalog)

    payload = json.dumps(
        [{"id": x["id"], "name": x.get("name", ""), "bio": (x.get("bio") or "")[:400],
          "categories": x.get("categories", ""), "titles": (x.get("product_sample") or "")[:500],
          "eco_percent": float(x.get("eco_percent") or 0)} for x in sellers_catalog],
        ensure_ascii=False,
    )
    schema = (
        'Ответь ТОЛЬКО JSON: {"ranked_ids":[числа id в порядке релевантности],'
        '"explanation":"1-3 предложения по-русски: почему эти мастерские подходят"}'
    )
    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT + " " + schema},
                {
                    "role": "user",
                    "content": f"Запрос покупателя: {q}\n\nПродавцы (JSON):\n{payload}\n\nВерни ranked_ids — подходящие первыми.",
                },
            ],
            temperature=0.4,
            max_tokens=600,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_match_sellers_json(raw, sellers_catalog)
    except Exception as e:
        out = _demo_match_sellers(q, sellers_catalog)
        out["explanation"] += f" (API: {e})"
        return out


def _parse_match_sellers_json(raw: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    valid_ids = {int(x["id"]) for x in catalog}
    try:
        data = json.loads(raw)
        ids = data.get("ranked_ids")
        if not isinstance(ids, list):
            ids = []
        ranked = [int(x) for x in ids if int(x) in valid_ids]
        for sid in valid_ids:
            if sid not in ranked:
                ranked.append(sid)
        expl = str(data.get("explanation", "")).strip() or "Подбор по запросу."
        return {"ranked_ids": ranked, "explanation": expl}
    except (json.JSONDecodeError, TypeError, ValueError):
        return _demo_match_sellers("", catalog)


def match_products_by_query(
    user_query: str,
    products_catalog: list[dict[str, Any]],
    model: Optional[str] = None,
) -> dict[str, Any]:
    """
    Подбор товаров под запрос покупателя (главная / витрина).
    catalog: id, title, description, category, price, is_eco, seller_name.
    Возвращает ranked_ids и explanation.
    """
    q = (user_query or "").strip()
    if not products_catalog:
        return {"ranked_ids": [], "explanation": "Нет товаров в каталоге."}
    client = _client()
    if not client:
        return _demo_match_products(q, products_catalog)

    payload = json.dumps(
        [
            {
                "id": x["id"],
                "title": (x.get("title") or "")[:120],
                "description": (x.get("description") or "")[:300],
                "category": x.get("category", ""),
                "price": float(x.get("price") or 0),
                "is_eco": bool(x.get("is_eco")),
                "seller_name": (x.get("seller_name") or "")[:80],
            }
            for x in products_catalog
        ],
        ensure_ascii=False,
    )
    schema = (
        'Ответь ТОЛЬКО JSON: {"ranked_ids":[id в порядке релевантности],'
        '"explanation":"1-3 предложения по-русски: почему эти товары подходят"}'
    )
    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT + " " + schema},
                {
                    "role": "user",
                    "content": f"Запрос: {q}\n\nТовары (JSON):\n{payload}\n\nВерни ranked_ids.",
                },
            ],
            temperature=0.45,
            max_tokens=700,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_match_products_json(raw, products_catalog)
    except Exception as e:
        out = _demo_match_products(q, products_catalog)
        out["explanation"] = (out.get("explanation") or "") + f" (API: {e})"
        return out


def _parse_match_products_json(raw: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    valid = {int(x["id"]) for x in catalog}
    try:
        data = json.loads(raw)
        ids = data.get("ranked_ids")
        if not isinstance(ids, list):
            ids = []
        ranked = [int(x) for x in ids if int(x) in valid]
        for pid in valid:
            if pid not in ranked:
                ranked.append(pid)
        expl = str(data.get("explanation", "")).strip() or "Подбор по запросу."
        return {"ranked_ids": ranked, "explanation": expl}
    except (json.JSONDecodeError, TypeError, ValueError):
        return _demo_match_products("", catalog)


def _demo_match_products(user_query: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    q = (user_query or "").lower()
    words = [w for w in re.findall(r"[\wа-яё]{2,}", q, flags=re.IGNORECASE) if len(w) > 1]
    scored: list[tuple[float, int]] = []
    for row in catalog:
        blob = (
            f"{row.get('title', '')} {row.get('description', '')} {row.get('category', '')} "
            f"{row.get('seller_name', '')}"
        ).lower()
        score = 0.0
        for w in words:
            wl = w.lower()
            if wl in blob:
                score += 2.0
        if any(x in q for x in ("эко", "eco", "эколог", "натуральн", "органик", "esg")):
            if row.get("is_eco") or "eco" in (row.get("category") or "").lower():
                score += 8.0
        if "подар" in q:
            if any(x in blob for x in ("подар", "набор", "мини", "уник", "ручн", "автор")):
                score += 4.0
        if "дерев" in q and ("дерев" in blob or "резьб" in blob or "лип" in blob):
            score += 5.0
        if any(x in q for x in ("керам", "ваз", "глин")) and any(
            x in blob for x in ("керам", "ваз", "глин", "терракот")
        ):
            score += 5.0
        if any(x in q for x in ("огород", "овощ", "свеж", "урожай")) and (
            "agro" in blob or "огур" in blob or "баклаж" in blob or "зерно" in blob
        ):
            score += 5.0
        scored.append((score, int(row["id"])))
    scored.sort(key=lambda t: (-t[0], t[1]))
    ranked_ids = [i for _, i in scored]
    expl = (
        f"Демо-подбор по «{user_query[:80]}»: совпадение слов и категорий. "
        "Укажите OPENAI_API_KEY для семантики."
    )
    return {"ranked_ids": ranked_ids, "explanation": expl}


def _demo_match_sellers(user_query: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    q = (user_query or "").lower()
    words = [w for w in re.findall(r"[\wа-яё]{2,}", q, flags=re.IGNORECASE) if len(w) > 1]
    scored: list[tuple[float, int]] = []
    for row in catalog:
        blob = (
            f"{row.get('name', '')} {row.get('bio', '')} {row.get('categories', '')} "
            f"{row.get('product_sample', '')}"
        ).lower()
        score = 0.0
        for w in words:
            wl = w.lower()
            if wl in blob:
                score += 2.5
        if any(x in q for x in ("эко", "eco", "эколог", "подар", "натуральн", "органик")):
            score += float(row.get("eco_percent") or 0) / 25.0
        if "дерев" in q and ("дерев" in blob or "резьб" in blob or "лип" in blob or "берез" in blob):
            score += 6.0
        if any(x in q for x in ("керам", "глин", "ваз", "горш")) and any(
            x in blob for x in ("керам", "глин", "ваз", "терракот", "гончар")
        ):
            score += 5.0
        if any(x in q for x in ("огород", "овощ", "гряд", "урожай", "свеж")) and (
            "agro" in blob or "огур" in blob or "баклаж" in blob or "зерно" in blob or "гряд" in blob
        ):
            score += 5.0
        if "текстил" in q or "ковёр" in q or "ковер" in q:
            if "текстил" in blob or "ковр" in blob or "помпон" in blob or "ткан" in blob:
                score += 4.0
        if "корзин" in q or "лоз" in q or "плет" in q:
            if "корзин" in blob or "лоз" in blob or "плет" in blob:
                score += 4.0
        scored.append((score, int(row["id"])))
    scored.sort(key=lambda t: (-t[0], t[1]))
    ranked_ids = [i for _, i in scored]
    expl = (
        f"Демо-подбор по запросу «{user_query[:100]}»: совпадение слов и ниш. "
        "Добавьте OPENAI_API_KEY для семантического ранжирования."
    )
    return {"ranked_ids": ranked_ids, "explanation": expl}


def analyze_seller_for_customer(
    seller_name: str,
    seller_bio: str,
    products: list[dict[str, Any]],
    eco_percent: float,
    model: Optional[str] = None,
) -> dict[str, str]:
    """
    Публичный анализ витрины для покупателя: сильные/слабые стороны, советы, потенциал.
    """
    name = seller_name or "Продавец"
    bio = (seller_bio or "")[:800]
    lines = [f"Мастерская: {name}", f"О себе: {bio}", f"Доля eco-товаров: {eco_percent}%", "Товары:"]
    for i, p in enumerate(products[:24], 1):
        lines.append(f"{i}. {p.get('title')} — {p.get('category')} — {p.get('price')} ₸")
    block = "\n".join(lines)
    schema = (
        'Ответь ТОЛЬКО JSON: {"strengths":"...", "weaknesses":"...", '
        '"recommendations":"...", "growth_potential":"..."} — на русском, по 2–5 предложений каждое поле.'
    )
    client = _client()
    if not client:
        return _demo_analyze_seller(name, len(products), eco_percent, bio)

    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT + " " + schema},
                {"role": "user", "content": "Оцени витрину продавца для покупателя:\n" + block},
            ],
            temperature=0.55,
            max_tokens=900,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_seller_analysis_json(raw, name, len(products), eco_percent)
    except Exception as e:
        out = _demo_analyze_seller(name, len(products), eco_percent, bio)
        out["weaknesses"] = f"{out['weaknesses']}\n(Ошибка API: {e})"
        return out


def _parse_seller_analysis_json(
    raw: str, name: str, n_products: int, eco_pct: float
) -> dict[str, str]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return {
            "strengths": str(data.get("strengths", "")).strip() or "—",
            "weaknesses": str(data.get("weaknesses", "")).strip() or "—",
            "recommendations": str(data.get("recommendations", "")).strip() or "—",
            "growth_potential": str(data.get("growth_potential", "")).strip() or "—",
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return _demo_analyze_seller(name, n_products, eco_pct, "")


def _demo_analyze_seller(name: str, n_products: int, eco_pct: float, bio: str) -> dict[str, str]:
    return {
        "strengths": (
            f"• Витрина «{name}» с {n_products} карточками с фото — понятный ассортимент.\n"
            f"• Доля позиций с eco/ESG-акцентом около {eco_pct}% — это плюс для осознанных покупок.\n"
            "• Локальный малый бизнес: часто гибкие условия и уникальные изделия."
        ),
        "weaknesses": (
            "• Демо-режим: на площадке пока нет накопленных отзывов — ориентируйтесь на описания и фото.\n"
            "• Уточняйте сроки изготовления и доставку в переписке с продавцом."
        ),
        "recommendations": (
            "• Сравните похожие лоты по цене и материалам в каталоге.\n"
            "• Если нужен подарок — ищите готовые позиции с коротким сроком или уточните кастом."
        ),
        "growth_potential": (
            "При расширении линейки и стабильной логистике такие мастерские хорошо масштабируются "
            "в нише handmade / eco. С OpenAI-анализом текст будет точнее под реальный каталог."
        ),
    }


def purchase_advice_for_product(
    title: str,
    description: str,
    category: str,
    is_eco: bool,
    price: float,
    seller_name: str,
    model: Optional[str] = None,
) -> dict[str, str]:
    """
    Совет AI перед покупкой: стоит ли брать, eco-оценка, плюсы и минусы.
    Ключи: worth_buying, eco_assessment, pros, cons.
    """
    block = (
        f"Товар: {title}\nКатегория: {category}\nЦена: {price} ₸\n"
        f"Eco-флаг: {is_eco}\nПродавец: {seller_name}\nОписание: {(description or '')[:900]}"
    )
    schema = (
        'Ответь ТОЛЬКО JSON: {"worth_buying":"1-3 предложения: стоит ли покупать и при каких условиях",'
        '"eco_assessment":"eco / ESG: насколько позиция выглядит экологичной",'
        '"pros":"плюсы в виде текста или маркеров",'
        '"cons":"минусы / на что обратить внимание"} — всё по-русски.'
    )
    client = _client()
    if not client:
        return _demo_purchase_advice(title, category, is_eco, price)

    mdl = _resolved_model(model)
    try:
        resp = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": HUB_SYSTEM_PROMPT + " " + schema},
                {"role": "user", "content": "Покупатель сомневается. Дай честный краткий разбор:\n" + block},
            ],
            temperature=0.5,
            max_tokens=650,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse_purchase_advice_json(raw, title, category, is_eco, price)
    except Exception as e:
        out = _demo_purchase_advice(title, category, is_eco, price)
        out["cons"] = f"{out['cons']}\n(Ошибка API: {e})"
        return out


def _parse_purchase_advice_json(
    raw: str, title: str, category: str, is_eco: bool, price: float
) -> dict[str, str]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return {
            "worth_buying": str(data.get("worth_buying", "")).strip() or "—",
            "eco_assessment": str(data.get("eco_assessment", "")).strip() or "—",
            "pros": str(data.get("pros", "")).strip() or "—",
            "cons": str(data.get("cons", "")).strip() or "—",
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return _demo_purchase_advice(title, category, is_eco, price)


def _demo_purchase_advice(title: str, category: str, is_eco: bool, price: float) -> dict[str, str]:
    eco_txt = (
        "Позиция с явным eco/ESG акцентом — смотрите упаковку и логистику у продавца."
        if (is_eco or category == "eco")
        else "Стандартная карточка: экологичность зависит от материалов и практик мастера — уточняйте."
    )
    return {
        "worth_buying": (
            f"Демо: «{title}» в категории «{category}» за {price:,.0f} ₸ — разумный формат для маркетплейса handmade. "
            "Сравните с похожими лотами и почитайте описание. С OPENAI_API_KEY совет будет персональнее."
        ),
        "eco_assessment": eco_txt,
        "pros": "• Локальное ремесло / малый бизнес\n• Часто уникальность изделия\n• Можно уточнить детали у продавца",
        "cons": "• Нет накопленных отзывов на платформе (MVP)\n• Сроки и доставку согласуйте отдельно",
    }


def _demo_credit_assessment(
    monthly_income: float, sales_count_30d: int, business_description: str
) -> dict[str, Any]:
    """
    Простая эвристика + текст для демонстрации на хакатоне без API.
    """
    score = 50
    if monthly_income >= 80000:
        score += 15
    elif monthly_income >= 40000:
        score += 8
    else:
        score -= 5
    if sales_count_30d >= 30:
        score += 20
    elif sales_count_30d >= 10:
        score += 10
    elif sales_count_30d < 3:
        score -= 15
    bl = (business_description or "").lower()
    if any(w in bl for w in ("эко", "bio", "органик", "ручн", "ремесл")):
        score += 5
    prob = max(25, min(92, score))
    if prob >= 70:
        risk = "low"
    elif prob >= 45:
        risk = "medium"
    else:
        risk = "high"
    summary = (
        f"Демо-оценка: доход {monthly_income:,.0f} ₸/мес, продаж за 30 дней: {sales_count_30d}. "
        "Модель (или эвристика) учитывает устойчивость ниши и активность. "
        "С реальным OpenAI ответ будет детальнее."
    )
    return {"risk": risk, "approval_probability": prob, "summary": summary}
