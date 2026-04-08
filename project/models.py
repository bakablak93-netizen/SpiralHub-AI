# -*- coding: utf-8 -*-
"""
Модели данных для SpiralHubAI (SQLite через SQLAlchemy).
Роли: buyer — покупатель, seller — продавец.
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Категории маркетплейса
CATEGORIES = ("eco", "handmade", "agro", "bio")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    # buyer | seller
    role = db.Column(db.String(20), nullable=False, default="buyer")
    display_name = db.Column(db.String(100), nullable=True)
    # Коротко о мастерской (публично на странице продавца)
    seller_bio = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship("Product", backref="seller", lazy="dynamic")
    credit_applications = db.relationship(
        "CreditApplication", backref="user", lazy="dynamic"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class FavoriteSeller(db.Model):
    """Избранные продавцы: покупатель (user_id) → продавец (seller_id)."""

    __tablename__ = "favorite_sellers"
    __table_args__ = (db.UniqueConstraint("user_id", "seller_id", name="uq_favorite_user_seller"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FavoriteProduct(db.Model):
    """Избранные товары пользователя."""

    __tablename__ = "favorite_products"
    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    price = db.Column(db.Numeric(12, 2), nullable=False)
    category = db.Column(db.String(32), nullable=False)  # eco, handmade, agro, bio
    # ESG: явная отметка «эко-товар» (доп. фильтр)
    is_eco = db.Column(db.Boolean, default=False, nullable=False)
    # Путь относительно static/, напр. products/wood.png
    image_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CreditApplication(db.Model):
    """Заявка на микрокредит: поля формы + MVP-скоринг + AI-пояснения."""

    __tablename__ = "credit_applications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Заявитель (имя в форме; может отличаться от display_name)
    applicant_name = db.Column(db.String(120), nullable=True)
    # Запрошенная сумма и показатели бизнеса
    requested_amount = db.Column(db.Numeric(14, 2), nullable=True)
    monthly_income = db.Column(db.Numeric(14, 2), nullable=False)
    sales_count_30d = db.Column(db.Integer, nullable=False)
    experience_months = db.Column(db.Integer, nullable=True)
    business_category = db.Column(db.String(32), nullable=True)  # eco, handmade, agro, bio
    business_description = db.Column(db.Text, nullable=False)
    # Результат формулы / скоринга
    risk_level = db.Column(db.String(20), nullable=True)  # low, medium, high
    approval_probability = db.Column(db.Integer, nullable=True)  # 0–100
    recommended_amount = db.Column(db.Numeric(14, 2), nullable=True)
    # ESG: бонус за eco/bio в формуле; флаг для UI «устойчивый бизнес»
    sustainable_business = db.Column(db.Boolean, default=False, nullable=False)
    # Рекомендация интерфейса: одобрить / доработать заявку
    decision_recommendation = db.Column(db.String(20), nullable=True)  # approve, improve
    # Статус рассмотрения (MVP: выставляется эвристикой после подачи)
    status = db.Column(db.String(20), nullable=False, default="pending")
    # Тексты AI
    ai_summary = db.Column(db.Text, nullable=True)
    ai_tips_improve = db.Column(db.Text, nullable=True)
    ai_tips_grow = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Order(db.Model):
    """Заказ на товар (MVP checkout, без реальной оплаты)."""

    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    # Зарегистрированный покупатель; гость — NULL, данные в buyer_*
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    total_price = db.Column(db.Numeric(12, 2), nullable=False)
    # pending — создан; completed — после имитации успешной оплаты
    status = db.Column(db.String(20), nullable=False, default="pending")
    buyer_name = db.Column(db.String(120), nullable=False)
    buyer_phone = db.Column(db.String(40), nullable=False)
    buyer_address = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    buyer_user = db.relationship("User", foreign_keys=[user_id], backref="orders_placed")
    product = db.relationship("Product", backref="orders")
