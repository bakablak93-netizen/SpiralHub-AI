# -*- coding: utf-8 -*-
"""
SpiralHubAI — Flask-приложение (MVP).
Запуск: из папки project → python app.py
"""
from __future__ import annotations

import mimetypes
import os
import uuid
from collections import Counter
from decimal import Decimal, InvalidOperation
from functools import wraps

from sqlalchemy import or_, text
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# Загружаем .env из папки проекта, даже если запуск из другой cwd
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 МБ


def _allowed_image_filename(name: str) -> bool:
    if not name or "." not in name:
        return False
    ext = name.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXT


def _static_file_exists(rel: str) -> bool:
    """Проверка, что файл есть в static/ (без path traversal)."""
    if not rel or not isinstance(rel, str):
        return False
    r = rel.strip().replace("\\", "/")
    if ".." in r or r.startswith("/"):
        return False
    return os.path.isfile(os.path.join(BASE_DIR, "static", r))


def _products_with_real_images(products: list) -> list:
    """Оставляет только товары с существующим файлом фото."""
    return [p for p in products if p.image_filename and _static_file_exists(p.image_filename)]


def _demo_seller_stats(products: list, user_id: int) -> dict:
    """
    Упрощённая «статистика» для MVP / хакатона (без реальных заказов в БД).
    Детерминированно от числа товаров и id пользователя.
    """
    n = len(products)
    sales = max(0, (user_id * 17 + n * 11) % 120 + n * 4)
    total_price = sum(float(p.price) for p in products) if products else 0.0
    revenue = round(total_price * 0.14 + sales * min(150.0, total_price / max(n, 1) * 0.08), 2)
    return {"product_count": n, "sales_count": sales, "estimated_revenue": revenue}


def _eco_stats(products: list) -> tuple[int, float]:
    """Число eco-товаров (флаг is_eco или категория eco) и доля в процентах."""
    n = len(products)
    if not n:
        return 0, 0.0
    eco_n = sum(1 for p in products if p.is_eco or p.category == "eco")
    pct = round(100.0 * eco_n / n, 1)
    return eco_n, pct


def _fake_seller_rating(seller_id: int) -> float:
    """Детерминированный «рейтинг» 3.7–5.0 для карточки продавца (MVP / хакатон)."""
    x = ((seller_id * 9301 + 49297) % 233280) / 233280.0
    return round(3.7 + x * 1.3, 1)


def _seller_showcase_products(seller: User) -> list:
    """Товары продавца с реальным файлом фото — как в каталоге витрины."""
    return _products_with_real_images(
        Product.query.filter_by(seller_id=seller.id).order_by(Product.id.desc()).limit(80).all()
    )


def _seller_card_dict(seller: User) -> dict | None:
    """Данные для карточки в каталоге продавцов; None если нет товаров с фото."""
    products = _seller_showcase_products(seller)
    if not products:
        return None
    _, eco_pct = _eco_stats(products)
    cats = sorted({p.category for p in products})
    rating = _fake_seller_rating(seller.id)
    is_eco_seller = eco_pct >= 35.0
    titles = " ".join(p.title for p in products[:20])
    name = seller.display_name or seller.email
    bio = (seller.seller_bio or "")[:400]
    blob = f"{name} {seller.email} {bio} {titles}".lower()
    return {
        "seller": seller,
        "products": products,
        "product_count": len(products),
        "categories": cats,
        "eco_percent": eco_pct,
        "is_eco_seller": is_eco_seller,
        "rating": rating,
        "titles_blob": titles,
        "search_blob": blob,
        "categories_str": ", ".join(cats),
    }


def _all_seller_cards() -> list[dict]:
    rows = User.query.filter_by(role="seller").order_by(User.display_name.asc()).all()
    out = []
    for s in rows:
        c = _seller_card_dict(s)
        if c:
            out.append(c)
    return out


def _filter_seller_cards(
    cards: list[dict],
    q: str,
    cat: str,
    eco_only: bool,
    min_rating: float | None,
    min_products: int | None,
) -> list[dict]:
    q = (q or "").strip().lower()
    words = [w for w in q.split() if len(w) > 1]
    res = []
    for c in cards:
        if min_products is not None and c["product_count"] < min_products:
            continue
        if min_rating is not None and c["rating"] < min_rating:
            continue
        if eco_only and not c["is_eco_seller"]:
            continue
        if cat in CATEGORIES and cat not in c["categories"]:
            continue
        if words:
            if not all(w in c["search_blob"] for w in words):
                continue
        res.append(c)
    return res


def _sort_seller_cards(cards: list[dict], ranked_ids: list[int] | None) -> list[dict]:
    if not ranked_ids:
        return sorted(
            cards,
            key=lambda c: (-c["rating"], (c["seller"].display_name or c["seller"].email or "").lower()),
        )
    pos = {sid: i for i, sid in enumerate(ranked_ids)}
    return sorted(
        cards,
        key=lambda c: (pos.get(c["seller"].id, 10_000), -c["rating"]),
    )


def _fake_product_popularity(product_id: int) -> int:
    """Псевдо-популярность для сортировки (MVP, без реальной аналитики)."""
    return (product_id * 7919 % 97) + 10


def _eco_percent_on_page(products: list) -> float:
    """Доля eco-товаров среди переданного списка карточек."""
    if not products:
        return 0.0
    n = sum(1 for p in products if p.is_eco or p.category == "eco")
    return round(100.0 * n / len(products), 1)


def _sort_storefront_products(
    products: list, sort_key: str, ranked_ids: list[int] | None
) -> list:
    if ranked_ids:
        pos = {pid: i for i, pid in enumerate(ranked_ids)}
        return sorted(
            products,
            key=lambda p: (pos.get(p.id, 10_000), -_fake_product_popularity(p.id)),
        )
    if sort_key == "price_asc":
        return sorted(products, key=lambda p: (float(p.price), -p.id))
    if sort_key == "price_desc":
        return sorted(products, key=lambda p: (-float(p.price), -p.id))
    if sort_key == "popular":
        return sorted(products, key=lambda p: (-_fake_product_popularity(p.id), -p.id))
    return sorted(products, key=lambda p: (-p.id,))


def _similar_products_exclude(product: Product, limit: int = 4) -> list:
    """Похожие товары (та же категория), только с файлом фото."""
    q = (
        Product.query.filter(Product.category == product.category, Product.id != product.id)
        .filter(Product.image_filename.isnot(None))
        .filter(Product.image_filename != "")
        .order_by(Product.id.desc())
        .limit(40)
        .all()
    )
    return _products_with_real_images(q)[:limit]


def _eco_alternative_products(product: Product, limit: int = 4) -> list:
    """Eco-альтернативы: другие лоты с eco-флагом или категорией eco."""
    q = (
        Product.query.filter(
            Product.id != product.id,
            or_(Product.is_eco.is_(True), Product.category == "eco"),
        )
        .filter(Product.image_filename.isnot(None))
        .filter(Product.image_filename != "")
        .order_by(Product.id.desc())
        .limit(40)
        .all()
    )
    return _products_with_real_images(q)[:limit]


def _save_product_image_file(storage) -> tuple[str | None, str | None]:
    """
    Сохраняет загруженный файл в static/uploads/. Возвращает (image_filename, error_message).
    image_filename — путь для url_for('static', filename=...), напр. uploads/abc.png
    """
    if not storage or not storage.filename:
        return None, None
    raw_name = secure_filename(storage.filename)
    if not _allowed_image_filename(raw_name):
        return None, "error.image_invalid"
    data = storage.read()
    if len(data) > MAX_IMAGE_BYTES:
        return None, "error.image_too_large"
    ext = raw_name.rsplit(".", 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, fname)
    with open(path, "wb") as out:
        out.write(data)
    return f"uploads/{fname}", None

from ai import (
    analyze_product_image,
    analyze_seller_for_customer,
    chat_completion,
    eco_recommendations_for_product,
    generate_product_description,
    is_demo_mode,
    match_products_by_query,
    match_sellers_by_query,
    purchase_advice_for_product,
    seller_dashboard_advice,
)
from credit import CREDIT_CATEGORIES, evaluate_application
from i18n import default_user_prefs, merged_prefs, normalize_locale, translate
from models import (
    CATEGORIES,
    CreditApplication,
    FavoriteProduct,
    FavoriteSeller,
    Order,
    Product,
    User,
    db,
)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    db_path = os.path.join(BASE_DIR, "database.db")
    _is_production = (
        os.environ.get("FLASK_ENV", "").lower() == "production"
        or os.environ.get("CRAFT_HUB_PRODUCTION", "").strip() == "1"
    )
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or "dev-secret-change-me",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_is_production,
        WTF_CSRF_TIME_LIMIT=None,
    )
    if test_config:
        app.config.update(test_config)

    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    from flask_wtf.csrf import CSRFProtect

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["500 per minute"],
        storage_uri="memory://",
        enabled=not app.config.get("TESTING", False),
    )
    CSRFProtect(app)

    db.init_app(app)

    @app.template_test("static_file")
    def static_file_exists(rel):
        return _static_file_exists(rel) if rel else False

    def _t(key: str, **kwargs) -> str:
        return translate(session.get("locale"), key, **kwargs)

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash(_t("flash.login_required"), "warning")
                return redirect(url_for("login", next=request.path))
            return f(*args, **kwargs)

        return decorated

    def seller_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash(_t("flash.seller_login"), "warning")
                return redirect(url_for("login"))
            u = db.session.get(User, session["user_id"])
            if not u or u.role != "seller":
                flash(_t("flash.seller_role"), "danger")
                return redirect(url_for("profile"))
            return f(*args, **kwargs)

        return decorated

    @app.context_processor
    def inject_globals():
        uid = session.get("user_id")
        user = db.session.get(User, uid) if uid else None
        loc = normalize_locale(session.get("locale"))
        prefs = merged_prefs(session.get("user_prefs"))

        def _(key: str, **kwargs):
            return translate(loc, key, **kwargs)

        return dict(
            current_user=user,
            demo_mode=is_demo_mode(),
            categories=CATEGORIES,
            _=_,
            locale=loc,
            user_prefs=prefs,
        )

    def _storefront_bundle():
        """Общий контекст для главной и /catalog: поиск, фильтры, сортировка, AI-порядок."""
        q_text = (request.args.get("q") or "").strip()
        cat = (request.args.get("category") or "").strip()
        eco_only = request.args.get("eco") == "1"
        sort_key = (request.args.get("sort") or "new").strip()
        if sort_key not in ("new", "price_asc", "price_desc", "popular"):
            sort_key = "new"
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)

        query = Product.query
        if q_text:
            like = f"%{q_text}%"
            query = query.filter(
                (Product.title.ilike(like)) | (Product.description.ilike(like))
            )
        if cat in CATEGORIES:
            query = query.filter(Product.category == cat)
        if eco_only:
            query = query.filter(Product.is_eco.is_(True))
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)

        query = query.filter(Product.image_filename.isnot(None)).filter(Product.image_filename != "")
        raw_list = query.order_by(Product.created_at.desc()).limit(200).all()
        products = _products_with_real_images(raw_list)

        use_ai = request.args.get("ai") == "1" and session.get("ai_product_ranked_ids")
        ranked_ids = session.get("ai_product_ranked_ids") if use_ai else None
        products = _sort_storefront_products(products, sort_key, ranked_ids)
        ai_explanation = session.get("ai_product_explanation") if use_ai else None

        seller_ids = {p.seller_id for p in products}
        sellers_by_id = {}
        if seller_ids:
            for u in User.query.filter(User.id.in_(seller_ids)).all():
                sellers_by_id[u.id] = u

        uid = session.get("user_id")
        favorite_product_ids: set[int] = set()
        if uid:
            favorite_product_ids = {
                r.product_id for r in FavoriteProduct.query.filter_by(user_id=uid).all()
            }

        eco_share = _eco_percent_on_page(products)
        featured = products[:6]
        popularity_by_id = {p.id: _fake_product_popularity(p.id) for p in products}

        return dict(
            products=products,
            featured=featured,
            search_q=q_text,
            filter_category=cat,
            eco_only=eco_only,
            sort_key=sort_key,
            min_price=min_price,
            max_price=max_price,
            ai_mode=bool(use_ai),
            ai_explanation=ai_explanation,
            sellers_by_id=sellers_by_id,
            favorite_product_ids=favorite_product_ids,
            eco_share=eco_share,
            popularity_by_id=popularity_by_id,
        )

    @app.route("/")
    def index():
        if request.args.get("clear_ai") == "1":
            session.pop("ai_product_ranked_ids", None)
            session.pop("ai_product_explanation", None)
            flash(_t("flash.ai_products_reset"), "info")
            return redirect(url_for("index"))
        return render_template("index.html", **_storefront_bundle())

    @app.route("/sellers")
    def sellers_list():
        """Каталог продавцов: поиск, фильтры, AI-подбор, избранное."""
        if request.args.get("clear_ai") == "1":
            session.pop("ai_seller_ranked_ids", None)
            session.pop("ai_seller_explanation", None)
            flash(_t("flash.ai_sellers_reset"), "info")
            return redirect(url_for("sellers_list"))

        q = (request.args.get("q") or "").strip()
        cat = (request.args.get("category") or "").strip()
        eco_only = request.args.get("eco") == "1"
        min_rating = request.args.get("min_rating", type=float)
        min_products = request.args.get("min_products", type=int)

        all_cards = _all_seller_cards()
        filtered = _filter_seller_cards(all_cards, q, cat, eco_only, min_rating, min_products)

        use_ai_order = request.args.get("ai") == "1" and session.get("ai_seller_ranked_ids")
        ranked_ids = session.get("ai_seller_ranked_ids") if use_ai_order else None
        seller_cards = _sort_seller_cards(filtered, ranked_ids)
        ai_explanation = session.get("ai_seller_explanation") if use_ai_order else None

        uid = session.get("user_id")
        favorite_ids: set[int] = set()
        favorite_sellers_users: list[User] = []
        if uid:
            fav_rows = FavoriteSeller.query.filter_by(user_id=uid).order_by(
                FavoriteSeller.created_at.desc()
            ).all()
            favorite_ids = {r.seller_id for r in fav_rows}
            for r in fav_rows:
                su = db.session.get(User, r.seller_id)
                if su and su.role == "seller" and _seller_card_dict(su):
                    favorite_sellers_users.append(su)

        return render_template(
            "sellers.html",
            seller_cards=seller_cards,
            search_q=q,
            filter_category=cat,
            eco_only=eco_only,
            min_rating=min_rating,
            min_products=min_products,
            ai_mode=bool(use_ai_order),
            ai_explanation=ai_explanation,
            favorite_ids=favorite_ids,
            favorite_sellers_users=favorite_sellers_users,
        )

    @app.route("/ai_seller_search", methods=["POST"])
    def ai_seller_search():
        """AI ранжирует продавцов под текстовый запрос; результат — порядок на /sellers?ai=1."""
        query = (request.form.get("query") or "").strip()
        if len(query) < 2:
            flash(_t("flash.query_short_sellers"), "warning")
            return redirect(url_for("sellers_list"))
        cards = _all_seller_cards()
        catalog = [
            {
                "id": c["seller"].id,
                "name": c["seller"].display_name or c["seller"].email,
                "bio": (c["seller"].seller_bio or "")[:500],
                "categories": c["categories_str"],
                "product_sample": c["titles_blob"][:600],
                "eco_percent": c["eco_percent"],
            }
            for c in cards
        ]
        result = match_sellers_by_query(query, catalog)
        session["ai_seller_ranked_ids"] = result.get("ranked_ids", [])
        session["ai_seller_explanation"] = (result.get("explanation") or "")[:2000]
        session.modified = True
        flash(_t("flash.sellers_rank_updated"), "success")
        return redirect(url_for("sellers_list", ai=1))

    @app.route("/favorite_seller", methods=["POST"])
    @login_required
    def favorite_seller():
        """Добавить / убрать продавца из избранного (POST: seller_id, action=toggle|add|remove)."""
        sid = request.form.get("seller_id", type=int)
        action = (request.form.get("action") or "toggle").strip().lower()
        nxt = (request.form.get("next") or "").strip() or request.referrer or url_for("sellers_list")
        if not sid:
            flash(_t("flash.seller_missing"), "danger")
            return redirect(nxt)
        seller = db.session.get(User, sid)
        if not seller or seller.role != "seller":
            flash(_t("flash.seller_not_found"), "danger")
            return redirect(nxt)
        uid = session["user_id"]
        if seller.id == uid:
            flash(_t("flash.cannot_favorite_self"), "warning")
            return redirect(nxt)
        row = FavoriteSeller.query.filter_by(user_id=uid, seller_id=sid).first()
        if action == "remove" or (action == "toggle" and row):
            if row:
                db.session.delete(row)
                db.session.commit()
                flash(_t("flash.removed_fav_seller"), "info")
        else:
            if not row:
                db.session.add(FavoriteSeller(user_id=uid, seller_id=sid))
                db.session.commit()
                flash(_t("flash.in_favorites_seller"), "success")
        return redirect(nxt)

    @app.route("/seller/<int:sid>")
    def seller_public(sid):
        u = db.session.get(User, sid)
        if not u or u.role != "seller":
            flash(_t("flash.seller_not_found_warn"), "warning")
            return redirect(url_for("sellers_list"))
        items = _seller_showcase_products(u)
        _, eco_pct = _eco_stats(items)
        cat_counts = Counter(p.category for p in items)
        stats = _demo_seller_stats(items, u.id)
        analysis = None
        stored = session.get("seller_profile_analysis")
        if isinstance(stored, dict) and stored.get("seller_id") == u.id:
            analysis = stored.get("data")

        uid = session.get("user_id")
        is_favorited = False
        if uid and uid != u.id:
            is_favorited = (
                FavoriteSeller.query.filter_by(user_id=uid, seller_id=u.id).first() is not None
            )

        return render_template(
            "seller_profile.html",
            seller=u,
            products=items,
            eco_percent=eco_pct,
            category_counts=cat_counts,
            stats=stats,
            analysis=analysis,
            is_favorited=is_favorited,
        )

    @app.route("/seller/<int:sid>/analyze", methods=["POST"])
    @login_required
    def seller_ai_analyze(sid):
        """AI-обзор витрины для покупателя (сильные/слабые стороны, рост)."""
        u = db.session.get(User, sid)
        if not u or u.role != "seller":
            flash(_t("flash.seller_not_found_warn"), "warning")
            return redirect(url_for("sellers_list"))
        items = _seller_showcase_products(u)
        _, eco_pct = _eco_stats(items)
        plist = [{"title": p.title, "category": p.category, "price": str(p.price)} for p in items[:30]]
        data = analyze_seller_for_customer(
            u.display_name or u.email,
            u.seller_bio or "",
            plist,
            eco_pct,
        )
        session["seller_profile_analysis"] = {"seller_id": sid, "data": data}
        session.modified = True
        flash(_t("flash.seller_analysis_ready"), "success")
        return redirect(url_for("seller_public", sid=sid))

    @limiter.limit("12 per minute")
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            role = request.form.get("role") or "buyer"
            name = (request.form.get("display_name") or "").strip()
            if role not in ("buyer", "seller"):
                role = "buyer"
            if not email or not password:
                flash(_t("flash.fill_email_password"), "danger")
                return render_template("register.html")
            if User.query.filter_by(email=email).first():
                flash(_t("flash.email_taken"), "danger")
                return render_template("register.html")
            u = User(email=email, role=role, display_name=name or None)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            session["user_id"] = u.id
            flash(_t("flash.welcome"), "success")
            return redirect(url_for("index"))
        return render_template("register.html")

    @limiter.limit("20 per minute")
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            u = User.query.filter_by(email=email).first()
            if u and u.check_password(password):
                session["user_id"] = u.id
                flash(_t("flash.logged_in"), "success")
                nxt = request.args.get("next") or url_for("index")
                return redirect(nxt)
            flash(_t("flash.bad_credentials"), "danger")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.pop("user_id", None)
        session.pop("chat_messages", None)
        session.pop("profile_ai_advice", None)
        session.pop("ai_product_ranked_ids", None)
        session.pop("ai_product_explanation", None)
        flash(_t("flash.logged_out"), "info")
        return redirect(url_for("index"))

    @app.route("/catalog")
    def catalog():
        if request.args.get("clear_ai") == "1":
            session.pop("ai_product_ranked_ids", None)
            session.pop("ai_product_explanation", None)
            flash(_t("flash.ai_products_reset"), "info")
            return redirect(url_for("catalog"))
        return render_template("catalog.html", **_storefront_bundle())

    @app.route("/ai_recommend", methods=["POST"])
    def ai_recommend():
        """AI подбирает товары под запрос; порядок на главной/каталоге с ?ai=1."""
        query = (request.form.get("query") or "").strip()
        if len(query) < 2:
            flash(_t("flash.query_short_products"), "warning")
            return redirect(request.referrer or url_for("index"))
        raw = (
            Product.query.filter(Product.image_filename.isnot(None))
            .filter(Product.image_filename != "")
            .order_by(Product.id.desc())
            .limit(120)
            .all()
        )
        items = _products_with_real_images(raw)
        catalog = []
        for p in items:
            seller = db.session.get(User, p.seller_id)
            catalog.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "description": (p.description or "")[:400],
                    "category": p.category,
                    "price": float(p.price),
                    "is_eco": p.is_eco,
                    "seller_name": (seller.display_name or seller.email) if seller else "",
                }
            )
        result = match_products_by_query(query, catalog)
        session["ai_product_ranked_ids"] = result.get("ranked_ids", [])
        session["ai_product_explanation"] = (result.get("explanation") or "")[:2000]
        session.modified = True
        flash(_t("flash.products_rank_updated"), "success")
        if (request.form.get("source") or "").strip() == "catalog":
            return redirect(url_for("catalog", ai=1))
        return redirect(url_for("index", ai=1))

    @app.route("/favorite", methods=["POST"])
    @login_required
    def favorite_product():
        """Избранное по товарам: product_id, action add|remove|toggle, next."""
        pid = request.form.get("product_id", type=int)
        action = (request.form.get("action") or "toggle").strip().lower()
        nxt = (request.form.get("next") or "").strip() or request.referrer or url_for("index")
        if not pid:
            flash(_t("flash.product_missing"), "danger")
            return redirect(nxt)
        product = db.session.get(Product, pid)
        if not product:
            flash(_t("flash.product_not_found"), "danger")
            return redirect(nxt)
        uid = session["user_id"]
        row = FavoriteProduct.query.filter_by(user_id=uid, product_id=pid).first()
        if action == "remove" or (action == "toggle" and row):
            if row:
                db.session.delete(row)
                db.session.commit()
                flash(_t("flash.removed_fav_product"), "info")
        else:
            if not row:
                db.session.add(FavoriteProduct(user_id=uid, product_id=pid))
                db.session.commit()
                flash(_t("flash.in_favorites_product"), "success")
        return redirect(nxt)

    @app.route("/favorites")
    @login_required
    def favorites_products():
        """Список избранных товаров (только с существующим фото файла)."""
        uid = session["user_id"]
        rows = FavoriteProduct.query.filter_by(user_id=uid).order_by(FavoriteProduct.created_at.desc()).all()
        pids = [r.product_id for r in rows]
        products = []
        sellers_by_id = {}
        if pids:
            for p in Product.query.filter(Product.id.in_(pids)).all():
                if p.image_filename and _static_file_exists(p.image_filename):
                    products.append(p)
            seller_ids = {p.seller_id for p in products}
            if seller_ids:
                for u in User.query.filter(User.id.in_(seller_ids)).all():
                    sellers_by_id[u.id] = u
        order = {pid: i for i, pid in enumerate(pids)}
        products.sort(key=lambda x: order.get(x.id, 9999))
        fav_ids = {p.id for p in products}
        return render_template(
            "favorites.html",
            products=products,
            sellers_by_id=sellers_by_id,
            favorite_product_ids=fav_ids,
        )

    @app.route("/product/<int:pid>")
    def product_detail(pid):
        p = db.session.get(Product, pid)
        if not p:
            flash(_t("flash.product_not_found_warn"), "warning")
            return redirect(url_for("index"))
        seller = db.session.get(User, p.seller_id)
        similar_q = (
            Product.query.filter(Product.category == p.category, Product.id != p.id)
            .filter(Product.image_filename.isnot(None))
            .filter(Product.image_filename != "")
            .order_by(Product.id.desc())
            .limit(24)
            .all()
        )
        similar = _products_with_real_images(similar_q)[:4]
        similar_sellers = {}
        if similar:
            sids = {x.seller_id for x in similar}
            for u in User.query.filter(User.id.in_(sids)).all():
                similar_sellers[u.id] = u

        uid = session.get("user_id")
        is_favorited = False
        if uid:
            is_favorited = (
                FavoriteProduct.query.filter_by(user_id=uid, product_id=p.id).first() is not None
            )

        if p.is_eco or p.category == "eco":
            eco_tier = "high"
        elif p.category in ("agro", "bio"):
            eco_tier = "mid"
        else:
            eco_tier = "base"
        eco_i18n = {
            "label": f"product.eco.{eco_tier}_label",
            "hint": f"product.eco.{eco_tier}_hint",
        }

        return render_template(
            "product.html",
            product=p,
            seller=seller,
            similar_products=similar,
            similar_sellers=similar_sellers,
            is_favorited=is_favorited,
            eco_i18n=eco_i18n,
        )

    @app.route("/api/ai/purchase-advice", methods=["POST"])
    def api_purchase_advice():
        """Совет AI перед покупкой (доступно без входа — гостевой checkout)."""
        data = request.get_json(force=True, silent=True) or {}
        pid = data.get("product_id")
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return jsonify({"error": _t("error.api.product_id")}), 400
        p = db.session.get(Product, pid)
        if not p:
            return jsonify({"error": _t("error.api.not_found")}), 404
        seller = db.session.get(User, p.seller_id)
        sn = (seller.display_name or seller.email) if seller else ""
        adv = purchase_advice_for_product(
            p.title,
            p.description or "",
            p.category,
            bool(p.is_eco),
            float(p.price),
            sn,
        )
        return jsonify(adv)

    @app.route("/checkout/<int:product_id>", methods=["GET", "POST"])
    def checkout(product_id):
        """Оформление заказа: товар, количество, контакты; имитация оплаты → completed."""
        p = db.session.get(Product, product_id)
        if not p:
            flash(_t("flash.product_not_found_warn"), "warning")
            return redirect(url_for("index"))
        seller = db.session.get(User, p.seller_id)
        uid = session.get("user_id")
        if uid and uid == p.seller_id:
            flash(_t("flash.checkout_own_product"), "danger")
            return redirect(url_for("product_detail", pid=p.id))

        if request.method == "POST":
            name = (request.form.get("buyer_name") or "").strip()
            phone = (request.form.get("buyer_phone") or "").strip()
            address = (request.form.get("buyer_address") or "").strip()
            try:
                qty = int(request.form.get("quantity") or "1")
            except ValueError:
                qty = 0
            if not name or len(name) < 2:
                flash(_t("flash.checkout_name"), "danger")
                return render_template("checkout.html", product=p, seller=seller, quantity=max(1, qty))
            if len(phone) < 8:
                flash(_t("flash.checkout_phone"), "danger")
                return render_template("checkout.html", product=p, seller=seller, quantity=max(1, qty))
            if len(address) < 8:
                flash(_t("flash.checkout_address"), "danger")
                return render_template("checkout.html", product=p, seller=seller, quantity=max(1, qty))
            if qty < 1 or qty > 99:
                flash(_t("flash.checkout_qty"), "danger")
                return render_template("checkout.html", product=p, seller=seller, quantity=1)

            unit = Decimal(str(p.price))
            total = unit * qty
            order = Order(
                user_id=uid,
                product_id=p.id,
                quantity=qty,
                unit_price=unit,
                total_price=total,
                status="pending",
                buyer_name=name,
                buyer_phone=phone,
                buyer_address=address,
            )
            db.session.add(order)
            db.session.flush()
            # MVP: мгновенная «успешная оплата»
            order.status = "completed"
            db.session.commit()
            flash(_t("flash.checkout_success_demo"), "success")
            return redirect(url_for("order_success", order_id=order.id))

        qty = request.args.get("quantity", type=int) or 1
        qty = max(1, min(99, qty))
        return render_template("checkout.html", product=p, seller=seller, quantity=qty)

    @app.route("/order_success")
    def order_success():
        """Страница после покупки: похожие и eco-альтернативы."""
        oid = request.args.get("order_id", type=int)
        order = db.session.get(Order, oid) if oid else None
        if not order or order.status != "completed":
            flash(_t("flash.order_not_found"), "warning")
            return redirect(url_for("index"))
        prod = db.session.get(Product, order.product_id)
        if not prod:
            flash(_t("flash.order_product_gone"), "warning")
            return redirect(url_for("index"))
        seller = db.session.get(User, prod.seller_id)
        similar = _similar_products_exclude(prod, 4)
        eco_alt = _eco_alternative_products(prod, 4)
        sim_sellers = {}
        if similar:
            for u in User.query.filter(User.id.in_({x.seller_id for x in similar})).all():
                sim_sellers[u.id] = u
        eco_sellers = {}
        if eco_alt:
            for u in User.query.filter(User.id.in_({x.seller_id for x in eco_alt})).all():
                eco_sellers[u.id] = u
        return render_template(
            "success.html",
            order=order,
            product=prod,
            seller=seller,
            similar_products=similar,
            similar_sellers=sim_sellers,
            eco_alternatives=eco_alt,
            eco_alt_sellers=eco_sellers,
        )

    @app.route("/add_product", methods=["GET", "POST"])
    @app.route("/product/create", methods=["GET", "POST"])  # совместимость со старыми ссылками
    @seller_required
    def add_product():
        """Форма добавления товара (шаблон add_product.html)."""
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            description = (request.form.get("description") or "").strip()
            category = (request.form.get("category") or "handmade").strip()
            is_eco = request.form.get("is_eco") == "1"
            try:
                price = Decimal(str(request.form.get("price") or "0").replace(",", "."))
            except (InvalidOperation, ValueError):
                flash(_t("flash.bad_price"), "danger")
                return render_template("add_product.html")
            if category not in CATEGORIES:
                category = "handmade"
            if not title:
                flash(_t("flash.need_title"), "danger")
                return render_template("add_product.html")

            image_rel = None
            upload = request.files.get("image")
            if upload and upload.filename:
                image_rel, up_err = _save_product_image_file(upload)
                if up_err:
                    flash(_t(up_err), "danger")
                    return render_template("add_product.html")

            p = Product(
                seller_id=session["user_id"],
                title=title,
                description=description,
                price=price,
                category=category,
                is_eco=is_eco,
                image_filename=image_rel,
            )
            db.session.add(p)
            db.session.commit()
            flash(_t("flash.product_created"), "success")
            return redirect(url_for("product_detail", pid=p.id))
        return render_template("add_product.html")

    @app.route("/product/<int:pid>/edit", methods=["GET", "POST"])
    @seller_required
    def product_edit(pid):
        """Редактирование карточки: только владелец."""
        p = db.session.get(Product, pid)
        if not p or p.seller_id != session["user_id"]:
            flash(_t("flash.product_not_yours"), "danger")
            return redirect(url_for("profile"))
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            description = (request.form.get("description") or "").strip()
            category = (request.form.get("category") or "handmade").strip()
            is_eco = request.form.get("is_eco") == "1"
            try:
                price = Decimal(str(request.form.get("price") or "0").replace(",", "."))
            except (InvalidOperation, ValueError):
                flash(_t("flash.bad_price"), "danger")
                return render_template("product_edit.html", product=p)
            if category not in CATEGORIES:
                category = "handmade"
            if not title:
                flash(_t("flash.need_title"), "danger")
                return render_template("product_edit.html", product=p)

            upload = request.files.get("image")
            if upload and upload.filename:
                image_rel, up_err = _save_product_image_file(upload)
                if up_err:
                    flash(_t(up_err), "danger")
                    return render_template("product_edit.html", product=p)
                p.image_filename = image_rel

            p.title = title
            p.description = description
            p.price = price
            p.category = category
            p.is_eco = is_eco
            db.session.commit()
            flash(_t("flash.product_updated"), "success")
            return redirect(url_for("product_detail", pid=p.id))
        return render_template("product_edit.html", product=p)

    @app.route("/delete_product", methods=["POST"])
    @seller_required
    def delete_product():
        """Удаление товара из профиля (POST + product_id)."""
        pid = request.form.get("product_id", type=int)
        p = db.session.get(Product, pid) if pid else None
        if not p or p.seller_id != session["user_id"]:
            flash(_t("flash.cannot_delete_product"), "danger")
            return redirect(url_for("profile"))
        db.session.delete(p)
        db.session.commit()
        flash(_t("flash.product_deleted"), "info")
        return redirect(url_for("profile"))

    @app.route("/ai_advice", methods=["POST"])
    @login_required
    def ai_advice():
        """Собирает каталог продавца и сохраняет AI-блок в сессии для страницы профиля."""
        u = db.session.get(User, session["user_id"])
        if not u:
            return redirect(url_for("login"))
        products_payload: list[dict] = []
        if u.role == "seller":
            for p in Product.query.filter_by(seller_id=u.id).order_by(Product.id.desc()).all():
                products_payload.append(
                    {
                        "title": p.title,
                        "price": str(p.price),
                        "category": p.category,
                        "description": (p.description or "")[:240],
                    }
                )
        advice = seller_dashboard_advice(
            u.display_name or u.email,
            u.role,
            products_payload,
        )
        session["profile_ai_advice"] = advice
        session.modified = True
        flash(_t("flash.ai_advice_updated"), "success")
        return redirect(url_for("profile"))

    @app.route("/profile")
    @login_required
    def profile():
        u = db.session.get(User, session["user_id"])
        my_products = []
        profile_stats = None
        eco_count, eco_percent = 0, 0.0
        if u and u.role == "seller":
            my_products = Product.query.filter_by(seller_id=u.id).order_by(Product.id.desc()).all()
            profile_stats = _demo_seller_stats(my_products, u.id)
            eco_count, eco_percent = _eco_stats(my_products)
        credits = []
        if u:
            credits = (
                CreditApplication.query.filter_by(user_id=u.id)
                .order_by(CreditApplication.created_at.desc())
                .limit(10)
                .all()
            )
        ai_advice = session.get("profile_ai_advice")
        role_label = _t("profile.role_seller") if u and u.role == "seller" else _t("profile.role_buyer")
        return render_template(
            "profile.html",
            my_products=my_products,
            credits=credits,
            profile_stats=profile_stats,
            eco_count=eco_count,
            eco_percent=eco_percent,
            ai_advice=ai_advice,
            role_label=role_label,
        )

    @app.route("/switch-account")
    @login_required
    def switch_account():
        session.pop("user_id", None)
        session.pop("chat_messages", None)
        session.pop("profile_ai_advice", None)
        flash(_t("flash.switch_account"), "info")
        return redirect(url_for("login"))

    @app.route("/profile/edit", methods=["GET", "POST"])
    @login_required
    def profile_edit():
        u = db.session.get(User, session["user_id"])
        if not u:
            return redirect(url_for("login"))
        if request.method == "POST":
            name = (request.form.get("display_name") or "").strip() or None
            bio = (request.form.get("seller_bio") or "").strip() or None
            cur_pwd = request.form.get("current_password") or ""
            new_pwd = request.form.get("new_password") or ""
            new_pwd2 = request.form.get("new_password2") or ""

            u.display_name = name
            if u.role == "seller":
                u.seller_bio = bio or None
            else:
                u.seller_bio = None

            if new_pwd or new_pwd2:
                if not new_pwd or not new_pwd2:
                    flash(_t("flash.password_new_incomplete"), "danger")
                    return render_template("profile_edit.html")
                if new_pwd != new_pwd2:
                    flash(_t("flash.password_mismatch"), "danger")
                    return render_template("profile_edit.html")
                if len(new_pwd) < 6:
                    flash(_t("flash.password_short"), "danger")
                    return render_template("profile_edit.html")
                if not u.check_password(cur_pwd):
                    flash(_t("flash.password_wrong_current"), "danger")
                    return render_template("profile_edit.html")
                u.set_password(new_pwd)

            db.session.commit()
            flash(_t("flash.profile_saved"), "success")
            return redirect(url_for("profile"))
        return render_template("profile_edit.html")

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def user_settings():
        prefs = merged_prefs(session.get("user_prefs"))
        if request.method == "POST":
            act = (request.form.get("action") or "").strip()
            if act == "cancel":
                return redirect(url_for("profile"))
            if act != "save":
                return redirect(url_for("user_settings"))
            theme = request.form.get("theme") or "light"
            if theme not in ("light", "dark"):
                theme = "light"
            fs = request.form.get("font_scale") or "md"
            if fs not in ("sm", "md", "lg"):
                fs = "md"
            cur = request.form.get("currency") or "RUB"
            if cur not in ("KZT", "RUB", "USD", "EUR"):
                cur = "RUB"
            new_prefs = {
                "theme": theme,
                "font_scale": fs,
                "currency": cur,
                "notif_push": "notif_push" in request.form,
                "notif_email": "notif_email" in request.form,
                "notif_sms": "notif_sms" in request.form,
                "notif_products": "notif_products" in request.form,
                "notif_promo": "notif_promo" in request.form,
                "notif_sellers": "notif_sellers" in request.form,
                "privacy_analytics": "privacy_analytics" in request.form,
                "privacy_personalized": "privacy_personalized" in request.form,
                "two_factor": "two_factor" in request.form,
            }
            session["user_prefs"] = new_prefs
            session.modified = True
            flash(translate(session.get("locale"), "settings.saved"), "success")
            return redirect(url_for("user_settings"))
        return render_template("settings.html", prefs=prefs)

    @app.post("/settings/lang")
    def set_locale():
        """Смена языка (доступно без входа — для сессии и последующих визитов)."""
        data = request.get_json(silent=True) or {}
        lang = data.get("lang") or request.form.get("lang")
        session["locale"] = normalize_locale(lang)
        session.modified = True
        if request.content_type and "application/json" in request.content_type:
            return jsonify(ok=True, locale=session["locale"])
        return redirect(request.referrer or url_for("index"))

    @app.post("/settings/delete-account")
    @login_required
    def settings_delete_account_demo():
        flash(translate(session.get("locale"), "settings.delete_demo"), "info")
        return redirect(url_for("user_settings"))

    @app.route("/privacy")
    def privacy_page():
        return render_template("privacy.html")

    @app.route("/terms")
    def terms_page():
        return render_template("terms.html")

    @app.route("/faq")
    def faq_page():
        return render_template("faq.html")

    @app.route("/chat", methods=["GET", "POST"])
    @login_required
    def chat():
        if "chat_messages" not in session:
            session["chat_messages"] = []

        if request.method == "POST":
            user_text = (request.form.get("message") or "").strip()
            if user_text:
                msgs = list(session["chat_messages"])
                msgs.append({"role": "user", "content": user_text})
                # Для API передаём только user/assistant (без дублирования system)
                api_msgs = [{"role": m["role"], "content": m["content"]} for m in msgs[-16:]]
                reply = chat_completion(api_msgs)
                msgs.append({"role": "assistant", "content": reply})
                session["chat_messages"] = msgs
                session.modified = True
            return redirect(url_for("chat"))

        return render_template("chat.html", messages=session.get("chat_messages", []))

    @app.route("/chat/clear", methods=["POST"])
    @login_required
    def chat_clear():
        session["chat_messages"] = []
        session.modified = True
        flash(_t("flash.chat_cleared"), "info")
        return redirect(url_for("chat"))

    @app.route("/credit", methods=["GET", "POST"])
    @login_required
    def credit():
        if request.method == "POST":
            name = (request.form.get("applicant_name") or "").strip()
            if len(name) < 2:
                flash(_t("flash.credit_name"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)

            try:
                amount = Decimal(str(request.form.get("requested_amount") or "0").replace(",", "."))
            except (InvalidOperation, ValueError):
                flash(_t("flash.credit_bad_amount"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)
            if amount < 1000 or amount > 5_000_000:
                flash(_t("flash.credit_amount_range"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)

            try:
                income = Decimal(str(request.form.get("monthly_income") or "0").replace(",", "."))
            except (InvalidOperation, ValueError):
                flash(_t("flash.credit_bad_income"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)
            if income < 0:
                flash(_t("flash.credit_income_negative"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)

            try:
                sales = int(request.form.get("sales_count_30d") or "0")
            except ValueError:
                flash(_t("flash.credit_bad_sales"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)
            if sales < 0:
                flash(_t("flash.credit_sales_negative"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)

            try:
                exp_m = int(request.form.get("experience_months") or "0")
            except ValueError:
                flash(_t("flash.credit_bad_exp"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)
            if exp_m < 0 or exp_m > 600:
                flash(_t("flash.credit_exp_range"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)

            category = (request.form.get("business_category") or "handmade").lower().strip()
            if category not in CREDIT_CATEGORIES:
                category = "handmade"

            desc = (request.form.get("business_description") or "").strip()
            if not desc or len(desc) < 15:
                flash(_t("flash.credit_desc_short"), "danger")
                return render_template("credit.html", categories=CREDIT_CATEGORIES)

            result = evaluate_application(
                name,
                amount,
                income,
                sales,
                exp_m,
                category,
                desc,
            )
            app_row = CreditApplication(
                user_id=session["user_id"],
                applicant_name=name,
                requested_amount=amount,
                monthly_income=income,
                sales_count_30d=sales,
                experience_months=exp_m,
                business_category=category,
                business_description=desc,
                risk_level=result["risk"],
                approval_probability=result["approval_probability"],
                recommended_amount=Decimal(str(result["recommended_amount"])),
                sustainable_business=bool(result["sustainable_business"]),
                decision_recommendation=result["decision_recommendation"],
                status=result["status"],
                ai_summary=result.get("summary"),
                ai_tips_improve=result.get("tips_improve"),
                ai_tips_grow=result.get("tips_grow"),
            )
            db.session.add(app_row)
            db.session.commit()
            flash(_t("flash.credit_sent"), "success")
            return redirect(url_for("credit_result", application_id=app_row.id))

        # int/str для tojson в шаблоне (скрипт «Заполнить примером»)
        example = {
            "name": "Алексей Ремесленников",
            "amount": 180000,
            "income": 72000,
            "sales": 22,
            "experience_months": 14,
            "category": "eco",
            "desc": "Студия керамики: эко-глазури, продажи на SpiralHubAI и ярмарках, "
            "повторные заказы от частных клиентов.",
        }
        return render_template("credit.html", example=example, categories=CREDIT_CATEGORIES)

    @app.route("/credit_result")
    @login_required
    def credit_result():
        raw_id = request.args.get("application_id", type=int)
        if not raw_id:
            flash(_t("flash.credit_app_missing"), "warning")
            return redirect(url_for("credit"))
        row = db.session.get(CreditApplication, raw_id)
        if not row or row.user_id != session["user_id"]:
            flash(_t("flash.credit_app_not_found"), "danger")
            return redirect(url_for("credit"))
        return render_template("credit_result.html", application=row)

    @app.route("/credit_history")
    @login_required
    def credit_history():
        items = (
            CreditApplication.query.filter_by(user_id=session["user_id"])
            .order_by(CreditApplication.created_at.desc())
            .all()
        )
        return render_template("credit_history.html", applications=items)

    @app.route("/purchase_history")
    @login_required
    def purchase_history():
        uid = session["user_id"]
        orders = (
            Order.query.filter_by(user_id=uid)
            .filter(Order.status == "completed")
            .order_by(Order.created_at.desc())
            .all()
        )
        products_by_id: dict[int, Product] = {}
        if orders:
            pids = {o.product_id for o in orders}
            for p in Product.query.filter(Product.id.in_(pids)).all():
                products_by_id[p.id] = p
        return render_template(
            "purchase_history.html",
            orders=orders,
            products_by_id=products_by_id,
        )

    # --- JSON API для форм (генерация описания, eco) ---

    @app.route("/api/ai/describe", methods=["POST"])
    @login_required
    def api_describe():
        data = request.get_json(force=True, silent=True) or {}
        title = (data.get("title") or "").strip()
        category = (data.get("category") or "handmade").strip()
        hints = (data.get("hints") or "").strip()
        if not title:
            return jsonify({"error": _t("error.api.title_required")}), 400
        text = generate_product_description(title, category, hints)
        return jsonify({"description": text})

    @app.route("/api/ai/analyze-product-image", methods=["POST"])
    @seller_required
    def api_analyze_product_image():
        """Vision: распознать товар на фото и вернуть название, категорию и 3 варианта описания."""
        f = request.files.get("image")
        if not f or not f.filename:
            return jsonify({"error": _t("error.api.no_image")}), 400
        if not _allowed_image_filename(f.filename):
            return jsonify({"error": _t("error.image_invalid")}), 400
        data = f.read()
        if len(data) > MAX_IMAGE_BYTES:
            return jsonify({"error": _t("error.image_too_large")}), 400
        mime = mimetypes.guess_type(f.filename)[0] or "image/jpeg"
        result = analyze_product_image(data, mime)
        return jsonify(result)

    @app.route("/api/ai/eco", methods=["POST"])
    @login_required
    def api_eco():
        data = request.get_json(force=True, silent=True) or {}
        pid = data.get("product_id")
        if pid:
            p = db.session.get(Product, int(pid))
            if not p:
                return jsonify({"error": _t("error.api.not_found")}), 404
            tips = eco_recommendations_for_product(p.title, p.description)
            return jsonify({"tips": tips})
        title = (data.get("title") or "Товар").strip()
        desc = (data.get("description") or "").strip()
        tips = eco_recommendations_for_product(title, desc)
        return jsonify({"tips": tips})

    def migrate_sqlite_columns():
        """Добавляет новые колонки в существующую SQLite без пересоздания БД."""
        engine = db.engine
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE products ADD COLUMN image_filename VARCHAR(255)"))
                conn.commit()
            except Exception:
                conn.rollback()
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN seller_bio TEXT"))
                conn.commit()
            except Exception:
                conn.rollback()
            try:
                conn.execute(text("ALTER TABLE products ADD COLUMN is_eco BOOLEAN DEFAULT 0"))
                conn.commit()
            except Exception:
                conn.rollback()
            # Расширение заявок на микрокредит (AI + финтех MVP)
            for stmt in (
                "ALTER TABLE credit_applications ADD COLUMN applicant_name VARCHAR(120)",
                "ALTER TABLE credit_applications ADD COLUMN requested_amount NUMERIC(14,2)",
                "ALTER TABLE credit_applications ADD COLUMN experience_months INTEGER",
                "ALTER TABLE credit_applications ADD COLUMN business_category VARCHAR(32)",
                "ALTER TABLE credit_applications ADD COLUMN recommended_amount NUMERIC(14,2)",
                "ALTER TABLE credit_applications ADD COLUMN sustainable_business BOOLEAN DEFAULT 0",
                "ALTER TABLE credit_applications ADD COLUMN decision_recommendation VARCHAR(20)",
                "ALTER TABLE credit_applications ADD COLUMN status VARCHAR(20) DEFAULT 'pending'",
                "ALTER TABLE credit_applications ADD COLUMN ai_tips_improve TEXT",
                "ALTER TABLE credit_applications ADD COLUMN ai_tips_grow TEXT",
            ):
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                except Exception:
                    conn.rollback()

    def ensure_user(
        email: str,
        *,
        role: str,
        display_name: str,
        password: str,
        seller_bio: str | None = None,
    ) -> User:
        u = User.query.filter_by(email=email).first()
        if u:
            if seller_bio and not u.seller_bio:
                u.seller_bio = seller_bio
            if display_name and not u.display_name:
                u.display_name = display_name
            return u
        u = User(email=email, role=role, display_name=display_name, seller_bio=seller_bio)
        u.set_password(password)
        db.session.add(u)
        db.session.flush()
        return u

    def ensure_product(
        seller: User,
        title: str,
        description: str,
        price: Decimal,
        category: str,
        is_eco: bool,
        image_filename: str | None,
    ) -> None:
        existing = Product.query.filter_by(seller_id=seller.id, title=title).first()
        if existing:
            if image_filename and not existing.image_filename:
                existing.image_filename = image_filename
            return
        db.session.add(
            Product(
                seller_id=seller.id,
                title=title,
                description=description,
                price=price,
                category=category,
                is_eco=is_eco,
                image_filename=image_filename,
            )
        )

    def seed_demo_catalog():
        """
        Демо: покупатель, несколько продавцов с разными нишами, товары с фото из static/products/.
        Повторный запуск не дублирует товары с тем же названием у того же продавца.
        """
        with app.app_context():
            db.create_all()
            migrate_sqlite_columns()
            if app.config.get("TESTING"):
                return

            MARKER_TITLE = "Набор деревянных статуэток в народном стиле"
            if Product.query.filter_by(title=MARKER_TITLE).first():
                return

            demo_pw = "demo123"
            ensure_user(
                "buyer@craft.demo",
                role="buyer",
                display_name="Покупатель Демо",
                password=demo_pw,
            )
            # Классический демо-продавец (лоты без фото — для совместимости)
            legacy = ensure_user(
                "seller@craft.demo",
                role="seller",
                display_name="Мастерская «Лесная линия»",
                password=demo_pw,
                seller_bio="Текстиль, мёд и садовые товары — с 2018 года.",
            )

            wood = ensure_user(
                "wood@demo.craft",
                role="seller",
                display_name="Мастер Иван — резьба по дереву",
                password=demo_pw,
                seller_bio="Ручная миниатюра в народном стиле: липа и берёза, льняное масло.",
            )
            maria = ensure_user(
                "garden@demo.craft",
                role="seller",
                display_name="Эко-огород Марии",
                password=demo_pw,
                seller_bio="Свежие овощи и экзотические культуры с собственных грядок.",
            )
            grain_farm = ensure_user(
                "grain@demo.craft",
                role="seller",
                display_name="Хутор «Золотое зерно»",
                password=demo_pw,
                seller_bio="Зерно и урожай с поля — для хозяйства и переработки.",
            )
            clay = ensure_user(
                "clay@demo.craft",
                role="seller",
                display_name="Ателье «Глина и солнце»",
                password=demo_pw,
                seller_bio="Керамика и терракота ручной работы: вазы, миниатюры, декор.",
            )
            textile = ensure_user(
                "textile@demo.craft",
                role="seller",
                display_name="Мастерская «Уют-текстиль»",
                password=demo_pw,
                seller_bio="Текстильный декор: ковры, дорожки, предметы из ткани.",
            )
            weave = ensure_user(
                "weave@demo.craft",
                role="seller",
                display_name="Плетение Марины",
                password=demo_pw,
                seller_bio="Корзины и плетёные аксессуары из лозы и натуральных материалов.",
            )

            db.session.commit()

            # Товары с фотографиями (файлы в static/products/)
            ensure_product(
                wood,
                MARKER_TITLE,
                "Пять фигурок в духе русской народной пластики: мальчик в кепке, бабушка в платке, "
                "дед с бородой, рыбак с уловом и гармонист. Липа/берёза, шлифовка и безопасные красители. "
                "Отличный подарок и украшение полки.",
                Decimal("12500.00"),
                "handmade",
                True,
                "products/wood_figurines.png",
            )
            ensure_product(
                maria,
                "Свежие огурцы с грядки",
                "Хрустящие огурцы, только что собранные: шипастая кожица, яркий вкус. "
                "Для салатов и домашних заготовок. Выращено без химии.",
                Decimal("320.00"),
                "agro",
                True,
                "products/cucumbers.png",
            )
            ensure_product(
                maria,
                "Баклажаны тёмно-фиолетовые",
                "Плотные баклажаны с глянцевой кожицей и зелёным чашелистиком. "
                "Для гриля, запекания, рататуя и мусаки.",
                Decimal("280.00"),
                "agro",
                True,
                "products/eggplants.png",
            )
            ensure_product(
                maria,
                "Питайя: растение в горшке с плодами",
                "Живое растение Hylocereus с ярко-розовыми плодами. Для теплицы, зимнего сада "
                "или коллекции экзотики. Уход и подсказки — в комплекте.",
                Decimal("4500.00"),
                "agro",
                True,
                "products/dragon_fruit_plants.png",
            )
            ensure_product(
                grain_farm,
                "Зерно урожая оптом (мешок / партия)",
                "Свежеубранное зерно с поля — для корма, посева или переработки. "
                "Партии от фермы, проверка влажности. Уточняйте объём при заказе.",
                Decimal("8500.00"),
                "agro",
                False,
                "products/bulk_grain.png",
            )
            ensure_product(
                clay,
                "Мини-ваза из терракоты",
                "Компактная ваза из терракоты: матовый корпус, внутри прозрачная глазурь — "
                "можно ставить воду для мини-букета или сухоцветов.",
                Decimal("890.00"),
                "handmade",
                True,
                "products/terracotta_mini_vase.png",
            )
            ensure_product(
                clay,
                "Ваза керамическая «Песчаные волны»",
                "Ручная керамика с глубоким рельефом, напоминающим дюны или кору. "
                "Матовая неглазурованная поверхность, каждая ваза уникальна.",
                Decimal("5200.00"),
                "handmade",
                True,
                "products/ceramic_rippled_vase.png",
            )
            ensure_product(
                clay,
                "Белая керамическая ваза с рельефом",
                "Глянцевый белый фарфор с вертикальным волнообразным орнаментом. "
                "Для интерьера в скандинавском или минималистичном стиле.",
                Decimal("4800.00"),
                "handmade",
                False,
                "products/white_embossed_vase.png",
            )
            ensure_product(
                clay,
                "Миниатюрная амфора из глины",
                "Две ручки, текстура ручного лепа. Для миниатюр, полки, подарка любителю истории.",
                Decimal("650.00"),
                "handmade",
                True,
                "products/mini_amphora.png",
            )
            ensure_product(
                clay,
                "Терракотовая ваза с гравировкой",
                "Тёплый оттенок глины, лёгкая гравировка по поясу вазы. "
                "Универсальный декор для гостиной или кухни.",
                Decimal("6200.00"),
                "handmade",
                True,
                "products/terracotta_vase_etched.png",
            )
            ensure_product(
                clay,
                "Керамика ручной работы (студийная)",
                "Предмет из серии студийной керамики — стабильные пропорции и натуральный тон глины.",
                Decimal("4100.00"),
                "handmade",
                True,
                "products/studio_pottery.png",
            )
            ensure_product(
                textile,
                "Ковёр из помпонов «Малина и графит»",
                "Круглый ковёр из мягких помпонов, концентрические кольца красного и чёрного. "
                "Тактильный акцент для детской, спальни или зоны отдыха.",
                Decimal("5400.00"),
                "handmade",
                False,
                "products/pompom_rug.png",
            )
            ensure_product(
                textile,
                "Ковёр-тряпичный в яркую полоску",
                "Полосы из переработанных лоскутов: оранж, бирюза, жёлтый, розовый. "
                "Эко-подход, плотное плетение, бахрома по краю.",
                Decimal("4200.00"),
                "eco",
                True,
                "products/rag_rug_stripes.png",
            )
            ensure_product(
                weave,
                "Плетёная корзина из лозы с ручкой",
                "Широкое дно, удобная дугообразная ручка. Для сбора урожая, декора или подарочного набора.",
                Decimal("3200.00"),
                "handmade",
                True,
                "products/wicker_basket.png",
            )

            # Небольшой набор «старых» лотов без фото у legacy-продавца
            legacy_samples = [
                (
                    "Липовый мёд, банка 500 г",
                    "Без нагрева, пасека Алтай. Стеклянная банка.",
                    Decimal("650.00"),
                    "agro",
                    True,
                ),
                (
                    "Семена овощей heirloom, микс",
                    "10 пакетов для органического огорода.",
                    Decimal("890.00"),
                    "agro",
                    True,
                ),
            ]
            for title, desc, price, cat, eco in legacy_samples:
                ensure_product(legacy, title, desc, price, cat, eco, None)

            # Демо-заказы (MVP checkout)
            buyer_demo = User.query.filter_by(email="buyer@craft.demo").first()
            p_figures = Product.query.filter_by(title=MARKER_TITLE).first()
            p_cuc = Product.query.filter_by(title="Свежие огурцы с грядки").first()
            if buyer_demo and p_figures and not Order.query.filter_by(buyer_phone="+79990001122").first():
                db.session.add(
                    Order(
                        user_id=buyer_demo.id,
                        product_id=p_figures.id,
                        quantity=1,
                        unit_price=p_figures.price,
                        total_price=p_figures.price,
                        status="completed",
                        buyer_name="Покупатель Демо",
                        buyer_phone="+79990001122",
                        buyer_address="г. Москва, ул. Ремесленная, д. 1, кв. 7",
                    )
                )
            if buyer_demo and p_cuc and not Order.query.filter_by(buyer_phone="+79990001123").first():
                db.session.add(
                    Order(
                        user_id=buyer_demo.id,
                        product_id=p_cuc.id,
                        quantity=3,
                        unit_price=p_cuc.price,
                        total_price=p_cuc.price * 3,
                        status="completed",
                        buyer_name="Покупатель Демо",
                        buyer_phone="+79990001123",
                        buyer_address="МО, демо-дача, снт «Огород»",
                    )
                )

            # Тестовые заявки на микрокредит (идемпотентно по маркеру в описании)
            def _seed_credit(user: User | None, marker: str, **kw) -> None:
                if not user:
                    return
                if CreditApplication.query.filter(
                    CreditApplication.user_id == user.id,
                    CreditApplication.business_description.contains(marker),
                ).first():
                    return
                base_desc = kw.pop("business_description", None) or "Демо-описание бизнеса"
                desc = base_desc + " " + marker
                db.session.add(CreditApplication(business_description=desc, user_id=user.id, **kw))

            wood_user = User.query.filter_by(email="wood@demo.craft").first()
            _seed_credit(
                wood_user,
                "[demo-credit-seed-a]",
                applicant_name="Иван Деревянцев",
                business_description="Столярка и изделия из дерева, eco-упаковка, продажи на маркетплейсе.",
                requested_amount=Decimal("150000.00"),
                monthly_income=Decimal("68000.00"),
                sales_count_30d=28,
                experience_months=18,
                business_category="eco",
                risk_level="low",
                approval_probability=78,
                recommended_amount=Decimal("150000.00"),
                sustainable_business=True,
                decision_recommendation="approve",
                status="approved",
                ai_summary="Демо: устойчивый профиль (eco), стабильные продажи — ориентир на одобрение.",
                ai_tips_improve="Поддерживайте оборот и прозрачность дохода.",
                ai_tips_grow="Масштабируйте линейку изделий с той же эко-упаковкой.",
            )
            clay_user = User.query.filter_by(email="clay@demo.craft").first()
            _seed_credit(
                clay_user,
                "[demo-credit-seed-b]",
                applicant_name="Студия «Глина и солнце»",
                business_description="Керамика ручной работы, посуда и декор, онлайн-заказы.",
                requested_amount=Decimal("400000.00"),
                monthly_income=Decimal("22000.00"),
                sales_count_30d=2,
                experience_months=4,
                business_category="handmade",
                risk_level="high",
                approval_probability=34,
                recommended_amount=Decimal("48000.00"),
                sustainable_business=False,
                decision_recommendation="improve",
                status="rejected",
                ai_summary="Демо: высокая сумма относительно дохода и мало продаж — повышенный риск.",
                ai_tips_improve="Снизьте сумму или нарастите продажи 30 дней.",
                ai_tips_grow="Запустите предзаказы и наборы «под ключ».",
            )
            if buyer_demo:
                _seed_credit(
                    buyer_demo,
                    "[demo-credit-seed-c]",
                    applicant_name="Покупатель Демо",
                    business_description="Bio-ниша, развитие витрины и осознанное потребление.",
                    requested_amount=Decimal("50000.00"),
                    monthly_income=Decimal("45000.00"),
                    sales_count_30d=8,
                    experience_months=9,
                    business_category="bio",
                    risk_level="medium",
                    approval_probability=56,
                    recommended_amount=Decimal("50000.00"),
                    sustainable_business=True,
                    decision_recommendation="improve",
                    status="pending",
                    ai_summary="Демо: средний профиль — заявка на доработку / ручной разбор.",
                    ai_tips_improve="Добавьте подтверждение дохода и план погашения.",
                    ai_tips_grow="Свяжите заявку с продажами на витрине SpiralHubAI.",
                )

            db.session.commit()

    seed_demo_catalog()
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
