# -*- coding: utf-8 -*-
"""
Микрокредиты SpiralHubAI: MVP-скоринг (формула) + AI-пояснения (ai.narrate_credit_assessment).

Формула не заменяет банковский скоринг; для демо и хакатона показатели
согласованы с полями формы: продажи, доход, стаж, категория, ESG-бонус.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from ai import narrate_credit_assessment

# Допустимые категории бизнеса (совпадают с нишами маркетплейса)
CREDIT_CATEGORIES = ("eco", "handmade", "agro", "bio")


def compute_credit_mvp(
    requested_amount: float,
    monthly_income: float,
    sales_count_30d: int,
    experience_months: int,
    business_category: str,
    business_description: str,
) -> dict[str, Any]:
    """
    Эвристический скор 20–94 → вероятность одобрения; риск и рекомендуемая сумма.

    Правила MVP:
    - больше продаж за 30 дней → выше скор (ниже риск);
    - выше доход → выше шанс;
    - категория eco / bio → устойчивый бизнес + бонус к скору;
    - стаж > 6 месяцев → бонус;
    - запрошенная сумма слишком велика относительно дохода → штраф.
    """
    income = max(float(monthly_income), 1.0)
    amount = max(float(requested_amount), 0.0)
    sales = int(sales_count_30d)
    exp_m = max(int(experience_months), 0)
    cat = (business_category or "handmade").lower().strip()
    if cat not in CREDIT_CATEGORIES:
        cat = "handmade"
    desc_lower = (business_description or "").lower()

    score = 50.0

    # Активность продаж
    if sales >= 40:
        score += 20.0
    elif sales >= 25:
        score += 15.0
    elif sales >= 15:
        score += 10.0
    elif sales >= 5:
        score += 4.0
    elif sales < 3:
        score -= 18.0

    # Доход
    if income >= 120_000:
        score += 18.0
    elif income >= 70_000:
        score += 12.0
    elif income >= 40_000:
        score += 6.0
    elif income < 25_000:
        score -= 14.0

    # Стаж: «> 6 месяцев» — бонус с 7-го месяца; доп. бонус от года
    if exp_m >= 12:
        score += 12.0
    elif exp_m > 6:
        score += 8.0

    # Категория и ESG
    if cat == "eco":
        score += 10.0
    elif cat == "bio":
        score += 8.0
    elif cat == "agro":
        score += 5.0
    else:
        score += 3.0  # handmade

    sustainable = cat in ("eco", "bio") or any(
        w in desc_lower for w in ("эко", "eco", "органик", "organic", "esg", "устойчив")
    )
    # ESG: явные eco/bio в описании при другой категории — небольшой бонус к скору
    if sustainable and cat not in ("eco", "bio"):
        score += 5.0

    # Долговая нагрузка (запрошенная сумма / месячный доход)
    leverage = amount / income if income else 0.0
    if leverage > 8:
        score -= 22.0
    elif leverage > 5:
        score -= 14.0
    elif leverage > 3:
        score -= 7.0

    prob = int(round(max(20.0, min(94.0, score))))

    if prob >= 73:
        risk = "low"
    elif prob >= 48:
        risk = "medium"
    else:
        risk = "high"

    # Рекомендуемая сумма: потолок от дохода и риска; устойчивому бизнесу чуть выше потолок
    cap_mult = 5.0 if risk == "low" else 3.5 if risk == "medium" else 2.2
    if sustainable:
        cap_mult *= 1.06
    recommended = min(amount, income * cap_mult)
    if recommended < 1 and amount >= 1:
        recommended = min(amount, income * 1.5)

    decision = "approve" if prob >= 58 and risk != "high" else "improve"

    return {
        "risk": risk,
        "approval_probability": prob,
        "recommended_amount": round(recommended, 2),
        "sustainable_business": sustainable,
        "decision_recommendation": decision,
    }


def derive_application_status(risk: str, prob: int, decision: str) -> str:
    """
    MVP-статус заявки после автоматической оценки (не банковский процесс).

    - Одобрено: высокая вероятность и не высокий риск.
    - Отклонено: высокий риск и низкая вероятность.
    - В остальных случаях — на доработку / ручной просмотр (pending).
    """
    if decision == "approve" and prob >= 62 and risk == "low":
        return "approved"
    if risk == "high" and prob < 42:
        return "rejected"
    if decision == "approve" and prob >= 55 and risk == "medium":
        return "approved"
    return "pending"


def evaluate_application(
    applicant_name: str,
    requested_amount: Decimal | float,
    monthly_income: Decimal | float,
    sales_count_30d: int,
    experience_months: int,
    business_category: str,
    business_description: str,
) -> dict[str, Any]:
    """
    Полная оценка: формула + OpenAI (или демо-тексты): объяснение и советы.
    """
    amt = float(requested_amount)
    inc = float(monthly_income)
    formula = compute_credit_mvp(
        amt,
        inc,
        sales_count_30d,
        experience_months,
        business_category,
        business_description,
    )
    narrative = narrate_credit_assessment(
        applicant_name=applicant_name,
        requested_amount=amt,
        monthly_income=inc,
        sales_count_30d=sales_count_30d,
        experience_months=experience_months,
        business_category=business_category,
        business_description=business_description,
        risk=formula["risk"],
        approval_probability=formula["approval_probability"],
        recommended_amount=formula["recommended_amount"],
        sustainable_business=formula["sustainable_business"],
        decision_recommendation=formula["decision_recommendation"],
    )
    status = derive_application_status(
        formula["risk"],
        formula["approval_probability"],
        formula["decision_recommendation"],
    )
    out = {
        **formula,
        "summary": narrative["summary"],
        "tips_improve": narrative["tips_improve"],
        "tips_grow": narrative["tips_grow"],
        "status": status,
    }
    return out
