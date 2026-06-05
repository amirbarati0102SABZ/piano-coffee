from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
from werkzeug.exceptions import RequestEntityTooLarge
from urllib.parse import urlparse
import os
import cloudinary
import cloudinary.uploader
import cloudinary.api


app = Flask(__name__)


# ==========================================================
# تنظیمات اصلی برنامه
# ==========================================================

app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

# حداکثر حجم آپلود: 16MB
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# فرمت‌های مجاز عکس
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "heic", "heif"}

# دسته‌بندی‌های مجاز
ALLOWED_CATEGORIES = ["گرم", "سرد", "ماچا", "دمنوش", "شیک"]

# ترتیب نمایش دسته‌بندی‌ها
CATEGORY_ORDER = ["گرم", "سرد", "ماچا", "دمنوش", "شیک"]


# ==========================================================
# تنظیمات Cloudinary
# پشتیبانی همزمان از:
# 1) CLOUDINARY_URL
# 2) CLOUDINARY_CLOUD_NAME + CLOUDINARY_API_KEY + CLOUDINARY_API_SECRET
# ==========================================================

CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "").strip()

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "").strip()
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "").strip()

EFFECTIVE_CLOUDINARY_CLOUD_NAME = None
EFFECTIVE_CLOUDINARY_API_KEY = None
EFFECTIVE_CLOUDINARY_API_SECRET = None


def configure_cloudinary():
    global EFFECTIVE_CLOUDINARY_CLOUD_NAME
    global EFFECTIVE_CLOUDINARY_API_KEY
    global EFFECTIVE_CLOUDINARY_API_SECRET

    # حالت اول: سه متغیر جداگانه در Render تنظیم شده باشند
    if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
        EFFECTIVE_CLOUDINARY_CLOUD_NAME = CLOUDINARY_CLOUD_NAME
        EFFECTIVE_CLOUDINARY_API_KEY = CLOUDINARY_API_KEY
        EFFECTIVE_CLOUDINARY_API_SECRET = CLOUDINARY_API_SECRET

        cloudinary.config(
            cloud_name=EFFECTIVE_CLOUDINARY_CLOUD_NAME,
            api_key=EFFECTIVE_CLOUDINARY_API_KEY,
            api_secret=EFFECTIVE_CLOUDINARY_API_SECRET,
            secure=True
        )

        print("Cloudinary configured using separate environment variables.")
        return

    # حالت دوم: فقط CLOUDINARY_URL در Render تنظیم شده باشد
    if CLOUDINARY_URL:
        try:
            parsed = urlparse(CLOUDINARY_URL)

            cloud_name = parsed.hostname
            api_key = parsed.username
            api_secret = parsed.password

            if cloud_name and api_key and api_secret:
                EFFECTIVE_CLOUDINARY_CLOUD_NAME = cloud_name
                EFFECTIVE_CLOUDINARY_API_KEY = api_key
                EFFECTIVE_CLOUDINARY_API_SECRET = api_secret

                cloudinary.config(
                    cloud_name=EFFECTIVE_CLOUDINARY_CLOUD_NAME,
                    api_key=EFFECTIVE_CLOUDINARY_API_KEY,
                    api_secret=EFFECTIVE_CLOUDINARY_API_SECRET,
                    secure=True
                )

                print("Cloudinary configured using CLOUDINARY_URL.")
                return

            print("CLOUDINARY_URL exists but could not be parsed correctly.")

        except Exception as e:
            print("Cloudinary URL parse error:", repr(e))

    # اگر هیچ تنظیم معتبری نبود
    cloudinary.config(secure=True)
    print("Cloudinary is NOT configured.")


configure_cloudinary()


def cloudinary_is_configured():
    return bool(
        EFFECTIVE_CLOUDINARY_CLOUD_NAME and
        EFFECTIVE_CLOUDINARY_API_KEY and
        EFFECTIVE_CLOUDINARY_API_SECRET
    )


# ==========================================================
# تنظیمات دیتابیس
# ==========================================================

database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///piano.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ==========================================================
# مدل دیتابیس
# ==========================================================

class Drink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


# ==========================================================
# توابع کمکی عمومی
# ==========================================================

def is_admin_logged_in():
    return session.get("admin") is True


def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def category_sort_index(category):
    if category in CATEGORY_ORDER:
        return CATEGORY_ORDER.index(category)
    return 999


# ==========================================================
# مدیریت تصاویر Cloudinary
# ==========================================================

def upload_image_to_cloudinary(image_file):
    """
    خروجی:
    {
        "success": True/False,
        "url": "...",
        "error": "..."
    }
    """

    if not cloudinary_is_configured():
        return {
            "success": False,
            "url": None,
            "error": (
                "Cloudinary روی Render درست به برنامه وصل نشده است. "
                "یا CLOUDINARY_URL را تنظیم کن، یا هر سه متغیر "
                "CLOUDINARY_CLOUD_NAME و CLOUDINARY_API_KEY و CLOUDINARY_API_SECRET را."
            )
        }

    if not image_file:
        return {
            "success": False,
            "url": None,
            "error": "فایل عکس از سمت فرم دریافت نشد."
        }

    if image_file.filename == "":
        return {
            "success": False,
            "url": None,
            "error": "نام فایل خالی است. احتمالاً عکسی انتخاب نشده است."
        }

    if not allowed_file(image_file.filename):
        return {
            "success": False,
            "url": None,
            "error": f"فرمت فایل مجاز نیست: {image_file.filename}"
        }

    try:
        image_file.stream.seek(0)

        result = cloudinary.uploader.upload(
            image_file,
            folder="piano-coffee",
            resource_type="image",
            use_filename=True,
            unique_filename=True,
            overwrite=False
        )

        secure_url = result.get("secure_url")

        if not secure_url:
            return {
                "success": False,
                "url": None,
                "error": "Cloudinary آپلود را انجام داد ولی secure_url برنگرداند."
            }

        return {
            "success": True,
            "url": secure_url,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "url": None,
            "error": f"خطای Cloudinary: {repr(e)}"
        }


def extract_public_id_from_url(image_url):
    try:
        if not image_url or "/upload/" not in image_url:
            return None

        after_upload = image_url.split("/upload/")[1]
        parts = after_upload.split("/")

        filtered_parts = []

        for part in parts:
            if part.startswith("v") and part[1:].isdigit():
                continue
            filtered_parts.append(part)

        if not filtered_parts:
            return None

        path = "/".join(filtered_parts)

        if "." in path:
            path = path.rsplit(".", 1)[0]

        return path

    except Exception:
        return None


def delete_image_from_cloudinary(image_url):
    if not cloudinary_is_configured():
        return False

    public_id = extract_public_id_from_url(image_url)

    if not public_id:
        return False

    try:
        cloudinary.uploader.destroy(
            public_id,
            invalidate=True,
            resource_type="image"
        )
        return True

    except Exception as e:
        print("Cloudinary delete error:", repr(e))
        return False


# ==========================================================
# مدیریت ترتیب نوشیدنی‌ها
# ==========================================================

def get_ordered_drinks():
    drinks = Drink.query.all()

    return sorted(
        drinks,
        key=lambda drink: (
            category_sort_index(drink.category),
            drink.sort_order or 0,
            drink.id
        )
    )


def get_next_sort_order(category):
    max_order = (
        db.session.query(db.func.max(Drink.sort_order))
        .filter_by(category=category)
        .scalar()
    )

    return (max_order or 0) + 1


def normalize_category_order(category):
    if not category:
        return

    drinks = (
        Drink.query
        .filter_by(category=category)
        .order_by(Drink.sort_order.asc(), Drink.id.asc())
        .all()
    )

    for index, drink in enumerate(drinks, start=1):
        drink.sort_order = index


def normalize_all_orders():
    for category in ALLOWED_CATEGORIES:
        normalize_category_order(category)

    db.session.commit()


def ensure_sort_order_column():
    try:
        inspector = inspect(db.engine)
        columns = [column["name"] for column in inspector.get_columns("drink")]

        if "sort_order" not in columns:
            db.session.execute(
                text("ALTER TABLE drink ADD COLUMN sort_order INTEGER DEFAULT 0 NOT NULL")
            )
            db.session.commit()
            print("sort_order column added successfully.")

        normalize_all_orders()

    except Exception as e:
        db.session.rollback()
        print("Sort order migration skipped or failed:", repr(e))


# ==========================================================
# ساخت جدول‌ها و اعمال تغییرات لازم روی دیتابیس
# ==========================================================

with app.app_context():
    db.create_all()
    ensure_sort_order_column()


# ==========================================================
# Error Handlers
# ==========================================================

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    return "حجم فایل بیش از حد مجاز است. حداکثر حجم مجاز 16 مگابایت است.", 413


@app.errorhandler(404)
def handle_not_found(error):
    return "صفحه یا آیتم مورد نظر پیدا نشد.", 404


@app.errorhandler(500)
def handle_server_error(error):
    return "خطای داخلی سرور رخ داد. لطفاً لاگ‌های Render را بررسی کنید.", 500


# ==========================================================
# مسیرهای سایت
# ==========================================================

@app.route("/")
def home():
    drinks = get_ordered_drinks()
    return render_template(
        "index.html",
        drinks=drinks,
        categories=ALLOWED_CATEGORIES
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin_username = os.environ.get("ADMIN_USERNAME")
        admin_password = os.environ.get("ADMIN_PASSWORD")

        if not admin_username or not admin_password:
            return "متغیرهای ADMIN_USERNAME و ADMIN_PASSWORD روی سرور تنظیم نشده‌اند."

        if username == admin_username and password == admin_password:
            session["admin"] = True
            return redirect(url_for("admin"))

        return "نام کاربری یا رمز عبور اشتباه است"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("home"))


@app.route("/admin")
def admin():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    drinks = get_ordered_drinks()

    total_count = Drink.query.count()
    hot_count = Drink.query.filter_by(category="گرم").count()
    cold_count = Drink.query.filter_by(category="سرد").count()
    matcha_count = Drink.query.filter_by(category="ماچا").count()
    herbal_count = Drink.query.filter_by(category="دمنوش").count()
    shake_count = Drink.query.filter_by(category="شیک").count()
    latest_drink = Drink.query.order_by(Drink.id.desc()).first()

    return render_template(
        "admin.html",
        drinks=drinks,
        categories=ALLOWED_CATEGORIES,
        total_count=total_count,
        hot_count=hot_count,
        cold_count=cold_count,
        matcha_count=matcha_count,
        herbal_count=herbal_count,
        shake_count=shake_count,
        latest_drink=latest_drink
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()
        image_file = request.files.get("image")

        if not name:
            return "نام نوشیدنی وارد نشده است."

        if not price:
            return "قیمت وارد نشده است."

        if not category:
            return "دسته‌بندی انتخاب نشده است."

        if not image_file or image_file.filename == "":
            return "عکس نوشیدنی انتخاب نشده است."

        if category not in ALLOWED_CATEGORIES:
            return "دسته‌بندی نامعتبر است."

        try:
            price = int(price)
        except ValueError:
            return "قیمت باید عدد باشد."

        if price < 0:
            return "قیمت نمی‌تواند منفی باشد."

        upload_result = upload_image_to_cloudinary(image_file)

        if not upload_result["success"]:
            return f"""
            <div style="font-family: sans-serif; direction: rtl; padding: 30px;">
                <h2>آپلود عکس ناموفق بود</h2>

                <p><strong>دلیل خطا:</strong></p>

                <pre style="background:#f3f3f3; padding:15px; border-radius:8px; direction:ltr; text-align:left; white-space:pre-wrap;">{upload_result["error"]}</pre>

                <hr>

                <p>وضعیت Cloudinary را از این صفحه چک کن:</p>
                <p>
                    <a href="{url_for('cloudinary_check')}">بررسی Cloudinary</a>
                </p>

                <hr>

                <a href="{url_for('add')}">بازگشت به افزودن نوشیدنی</a>
            </div>
            """

        new_drink = Drink(
            name=name,
            price=price,
            image=upload_result["url"],
            category=category,
            sort_order=get_next_sort_order(category)
        )

        db.session.add(new_drink)
        db.session.commit()

        return redirect(url_for("admin"))

    return render_template(
        "add.html",
        categories=ALLOWED_CATEGORIES
    )


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    drink = db.session.get(Drink, id)

    if not drink:
        return "نوشیدنی مورد نظر پیدا نشد.", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()

        if not name:
            return "نام نوشیدنی وارد نشده است."

        if not price:
            return "قیمت وارد نشده است."

        if not category:
            return "دسته‌بندی انتخاب نشده است."

        if category not in ALLOWED_CATEGORIES:
            return "دسته‌بندی نامعتبر است."

        try:
            price = int(price)
        except ValueError:
            return "قیمت باید عدد باشد."

        if price < 0:
            return "قیمت نمی‌تواند منفی باشد."

        old_category = drink.category
        old_image = drink.image

        drink.name = name
        drink.price = price

        if category != old_category:
            drink.category = category
            drink.sort_order = get_next_sort_order(category)
        else:
            drink.category = category

        image_file = request.files.get("image")

        if image_file and image_file.filename != "":
            upload_result = upload_image_to_cloudinary(image_file)

            if not upload_result["success"]:
                return f"""
                <div style="font-family: sans-serif; direction: rtl; padding: 30px;">
                    <h2>آپلود عکس جدید ناموفق بود</h2>

                    <p><strong>دلیل خطا:</strong></p>

                    <pre style="background:#f3f3f3; padding:15px; border-radius:8px; direction:ltr; text-align:left; white-space:pre-wrap;">{upload_result["error"]}</pre>

                    <hr>

                    <p>
                        <a href="{url_for('cloudinary_check')}">بررسی Cloudinary</a>
                    </p>

                    <a href="{url_for('edit', id=drink.id)}">بازگشت به ویرایش نوشیدنی</a>
                </div>
                """

            drink.image = upload_result["url"]

            if old_image:
                delete_image_from_cloudinary(old_image)

        db.session.commit()

        normalize_category_order(old_category)
        normalize_category_order(category)
        db.session.commit()

        return redirect(url_for("admin"))

    return render_template(
        "edit.html",
        drink=drink,
        categories=ALLOWED_CATEGORIES
    )


@app.route("/move/<int:id>/<direction>", methods=["POST"])
def move_drink(id, direction):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    if direction not in ["up", "down", "top", "bottom"]:
        return redirect(url_for("admin"))

    drink = db.session.get(Drink, id)

    if not drink:
        return "نوشیدنی مورد نظر پیدا نشد.", 404

    same_category_drinks = (
        Drink.query
        .filter_by(category=drink.category)
        .order_by(Drink.sort_order.asc(), Drink.id.asc())
        .all()
    )

    for index, item in enumerate(same_category_drinks, start=1):
        item.sort_order = index

    db.session.commit()

    same_category_drinks = (
        Drink.query
        .filter_by(category=drink.category)
        .order_by(Drink.sort_order.asc(), Drink.id.asc())
        .all()
    )

    current_index = None

    for index, item in enumerate(same_category_drinks):
        if item.id == drink.id:
            current_index = index
            break

    if current_index is None:
        return redirect(url_for("admin"))

    if direction == "up":
        if current_index > 0:
            other = same_category_drinks[current_index - 1]
            drink.sort_order, other.sort_order = other.sort_order, drink.sort_order
            db.session.commit()

    elif direction == "down":
        if current_index < len(same_category_drinks) - 1:
            other = same_category_drinks[current_index + 1]
            drink.sort_order, other.sort_order = other.sort_order, drink.sort_order
            db.session.commit()

    elif direction == "top":
        reordered = [item for item in same_category_drinks if item.id != drink.id]
        reordered.insert(0, drink)

        for index, item in enumerate(reordered, start=1):
            item.sort_order = index

        db.session.commit()

    elif direction == "bottom":
        reordered = [item for item in same_category_drinks if item.id != drink.id]
        reordered.append(drink)

        for index, item in enumerate(reordered, start=1):
            item.sort_order = index

        db.session.commit()

    normalize_category_order(drink.category)
    db.session.commit()

    return redirect(url_for("admin"))


@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    drink = db.session.get(Drink, id)

    if not drink:
        return "نوشیدنی مورد نظر پیدا نشد.", 404

    category = drink.category
    image_url = drink.image

    db.session.delete(drink)
    db.session.commit()

    if image_url:
        delete_image_from_cloudinary(image_url)

    normalize_category_order(category)
    db.session.commit()

    return redirect(url_for("admin"))


@app.route("/cloudinary-check")
def cloudinary_check():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    status = {
        "CLOUDINARY_URL_RAW_EXISTS": bool(CLOUDINARY_URL),
        "CLOUDINARY_CLOUD_NAME_RAW_EXISTS": bool(CLOUDINARY_CLOUD_NAME),
        "CLOUDINARY_API_KEY_RAW_EXISTS": bool(CLOUDINARY_API_KEY),
        "CLOUDINARY_API_SECRET_RAW_EXISTS": bool(CLOUDINARY_API_SECRET),
        "EFFECTIVE_CLOUDINARY_CLOUD_NAME": bool(EFFECTIVE_CLOUDINARY_CLOUD_NAME),
        "EFFECTIVE_CLOUDINARY_API_KEY": bool(EFFECTIVE_CLOUDINARY_API_KEY),
        "EFFECTIVE_CLOUDINARY_API_SECRET": bool(EFFECTIVE_CLOUDINARY_API_SECRET),
        "CONFIGURED": cloudinary_is_configured()
    }

    return f"""
    <div style="font-family: sans-serif; direction: rtl; padding: 30px; line-height: 1.9;">
        <h2>بررسی تنظیمات Cloudinary</h2>

        <h3>متغیرهایی که مستقیم از Render خوانده شده‌اند:</h3>

        <p>CLOUDINARY_URL وجود دارد؟ <strong>{status["CLOUDINARY_URL_RAW_EXISTS"]}</strong></p>
        <p>CLOUDINARY_CLOUD_NAME وجود دارد؟ <strong>{status["CLOUDINARY_CLOUD_NAME_RAW_EXISTS"]}</strong></p>
        <p>CLOUDINARY_API_KEY وجود دارد؟ <strong>{status["CLOUDINARY_API_KEY_RAW_EXISTS"]}</strong></p>
        <p>CLOUDINARY_API_SECRET وجود دارد؟ <strong>{status["CLOUDINARY_API_SECRET_RAW_EXISTS"]}</strong></p>

        <hr>

        <h3>وضعیت نهایی اتصال برنامه به Cloudinary:</h3>

        <p>Cloud Name نهایی معتبر است؟ <strong>{status["EFFECTIVE_CLOUDINARY_CLOUD_NAME"]}</strong></p>
        <p>API Key نهایی معتبر است؟ <strong>{status["EFFECTIVE_CLOUDINARY_API_KEY"]}</strong></p>
        <p>API Secret نهایی معتبر است؟ <strong>{status["EFFECTIVE_CLOUDINARY_API_SECRET"]}</strong></p>

        <h2>CONFIGURED: <strong>{status["CONFIGURED"]}</strong></h2>

        <hr>

        <p>
            اگر <strong>CONFIGURED</strong> برابر <strong>True</strong> باشد، یعنی برنامه Cloudinary را شناخته و آپلود باید از نظر تنظیمات Cloudinary ممکن باشد.
        </p>

        <p>
            اگر CLOUDINARY_URL برابر True باشد ولی سه متغیر جداگانه False باشند، مشکلی نیست.
            این نسخه از کد CLOUDINARY_URL را هم پشتیبانی می‌کند.
        </p>

        <a href="{url_for('admin')}">بازگشت به پنل مدیریت</a>
    </div>
    """


# ==========================================================
# اجرای برنامه
# ==========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
