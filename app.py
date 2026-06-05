from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
import os
import cloudinary
import cloudinary.uploader
import cloudinary.api

app = Flask(__name__)

# Secret Key برای Session
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

# تنظیمات Cloudinary
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

# حداکثر حجم آپلود: 15MB
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

# فرمت‌های مجاز عکس
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "heic", "heif"}

# دسته‌بندی‌های مجاز
ALLOWED_CATEGORIES = ["گرم", "سرد", "ماچا", "دمنوش", "شیک"]

# ترتیب نمایش دسته‌بندی‌ها
CATEGORY_ORDER = ["گرم", "سرد", "ماچا", "دمنوش", "شیک"]

# دیتابیس
database_url = os.environ.get("DATABASE_URL")

# بعضی وقت‌ها Render آدرس را با postgres:// می‌دهد، SQLAlchemy جدید postgresql:// می‌خواهد
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///piano.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# مدل نوشیدنی
class Drink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


def is_admin_logged_in():
    return session.get("admin") is True


def allowed_file(filename):
    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def upload_image_to_cloudinary(image_file):
    """
    آپلود عکس در Cloudinary
    خروجی: secure_url عکس
    """
    if not image_file or image_file.filename == "":
        return None

    if not allowed_file(image_file.filename):
        return None

    try:
        result = cloudinary.uploader.upload(
            image_file,
            folder="piano-coffee",
            resource_type="image"
        )
        return result.get("secure_url")
    except Exception as e:
        print("Cloudinary upload error:", e)
        return None


def delete_image_from_cloudinary(image_url):
    """
    حذف عکس از Cloudinary بر اساس URL ذخیره‌شده
    """
    try:
        if not image_url or "cloudinary.com" not in image_url:
            return

        # نمونه URL:
        # https://res.cloudinary.com/<cloud_name>/image/upload/v1234567890/piano-coffee/abc.jpg
        upload_part = "/upload/"
        if upload_part not in image_url:
            return

        public_part = image_url.split(upload_part, 1)[1]

        # حذف نسخه v123...
        parts = public_part.split("/")
        if len(parts) < 2:
            return

        if parts[0].startswith("v"):
            parts = parts[1:]

        public_id_with_ext = "/".join(parts)

        # حذف پسوند فایل
        public_id = os.path.splitext(public_id_with_ext)[0]

        cloudinary.uploader.destroy(public_id, resource_type="image")
    except Exception as e:
        print("Cloudinary delete error:", e)


def category_sort_index(category):
    """
    مشخص کردن ترتیب دسته‌بندی‌ها.
    اگر دسته‌بندی ناشناخته باشد، آخر لیست قرار می‌گیرد.
    """
    if category in CATEGORY_ORDER:
        return CATEGORY_ORDER.index(category)
    return 999


def get_ordered_drinks():
    """
    دریافت نوشیدنی‌ها با ترتیب نهایی:
    اول بر اساس دسته‌بندی، بعد sort_order، بعد id
    """
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
    """
    برای نوشیدنی جدید، آخرین sort_order همان دسته‌بندی را می‌گیرد
    و آیتم جدید را به انتهای همان دسته اضافه می‌کند.
    """
    max_order = (
        db.session.query(db.func.max(Drink.sort_order))
        .filter_by(category=category)
        .scalar()
    )

    return (max_order or 0) + 1


def normalize_category_order(category):
    """
    مرتب‌سازی مجدد شماره‌های sort_order داخل یک دسته‌بندی.
    این تابع باعث می‌شود ترتیب‌ها همیشه 1، 2، 3، ... باشند.
    """
    drinks = (
        Drink.query
        .filter_by(category=category)
        .order_by(Drink.sort_order.asc(), Drink.id.asc())
        .all()
    )

    for index, drink in enumerate(drinks, start=1):
        drink.sort_order = index


def normalize_all_orders():
    """
    مرتب‌سازی همه دسته‌بندی‌ها.
    مخصوصاً بعد از اضافه شدن ستون sort_order به دیتابیس قدیمی مفید است.
    """
    for category in ALLOWED_CATEGORIES:
        normalize_category_order(category)

    db.session.commit()


def ensure_sort_order_column():
    """
    اگر دیتابیس قبلاً ساخته شده باشد، ستون sort_order داخل جدول drink وجود ندارد.
    این تابع ستون sort_order را بدون پاک کردن اطلاعات قبلی اضافه می‌کند.
    """
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
        print("Sort order migration skipped or failed:", e)


# ساخت جدول‌ها و اعمال تغییرات لازم روی دیتابیس
with app.app_context():
    db.create_all()
    ensure_sort_order_column()


# صفحه اصلی مشتری
@app.route("/")
def home():
    drinks = get_ordered_drinks()
    return render_template(
        "index.html",
        drinks=drinks,
        categories=ALLOWED_CATEGORIES
    )


# ورود مدیریت
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        admin_username = os.environ.get("ADMIN_USERNAME")
        admin_password = os.environ.get("ADMIN_PASSWORD")

        # اگر روی سرور متغیرها تنظیم نشده باشند، ورود انجام نشود
        if not admin_username or not admin_password:
            return "متغیرهای ADMIN_USERNAME و ADMIN_PASSWORD روی سرور تنظیم نشده‌اند."

        if username == admin_username and password == admin_password:
            session["admin"] = True
            return redirect(url_for("admin"))

        return "نام کاربری یا رمز عبور اشتباه است"

    return render_template("login.html")


# خروج
@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("home"))


# پنل مدیریت + داشبورد
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


# افزودن نوشیدنی
@app.route("/add", methods=["GET", "POST"])
def add():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()
        image_file = request.files.get("image")

        if not name or not price or not category or not image_file:
            return "لطفاً همه فیلدها را کامل وارد کنید"

        if category not in ALLOWED_CATEGORIES:
            return "دسته‌بندی نامعتبر است"

        try:
            price = int(price)
        except ValueError:
            return "قیمت باید عدد باشد"

        if price < 0:
            return "قیمت نمی‌تواند منفی باشد"

        image_url = upload_image_to_cloudinary(image_file)

        if not image_url:
            return "آپلود عکس ناموفق بود یا فرمت عکس مجاز نیست. فرمت‌های مجاز: png، jpg، jpeg، webp، heic، heif"

        new_drink = Drink(
            name=name,
            price=price,
            image=image_url,
            category=category,
            sort_order=get_next_sort_order(category)
        )

        db.session.add(new_drink)
        db.session.commit()

        return redirect(url_for("admin"))

    return render_template("add.html", categories=ALLOWED_CATEGORIES)


# ویرایش نوشیدنی
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    drink = Drink.query.get_or_404(id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()

        if not name or not price or not category:
            return "لطفاً همه فیلدها را کامل وارد کنید"

        if category not in ALLOWED_CATEGORIES:
            return "دسته‌بندی نامعتبر است"

        try:
            price = int(price)
        except ValueError:
            return "قیمت باید عدد باشد"

        if price < 0:
            return "قیمت نمی‌تواند منفی باشد"

        old_category = drink.category

        drink.name = name
        drink.price = price

        # اگر دسته‌بندی تغییر کند، نوشیدنی به انتهای دسته‌بندی جدید منتقل می‌شود
        if category != old_category:
            drink.category = category
            drink.sort_order = get_next_sort_order(category)
        else:
            drink.category = category

        image_file = request.files.get("image")

        # اگر عکس جدید انتخاب شد
        if image_file and image_file.filename != "":
            image_url = upload_image_to_cloudinary(image_file)

            if not image_url:
                return "آپلود عکس ناموفق بود یا فرمت عکس مجاز نیست. فرمت‌های مجاز: png، jpg، jpeg، webp، heic، heif"

            # حذف عکس قبلی از Cloudinary
            delete_image_from_cloudinary(drink.image)

            drink.image = image_url

        db.session.commit()

        # بعد از تغییر دسته‌بندی، ترتیب هر دو دسته مرتب شود
        normalize_category_order(old_category)
        normalize_category_order(category)
        db.session.commit()

        return redirect(url_for("admin"))

    return render_template("edit.html", drink=drink, categories=ALLOWED_CATEGORIES)


# جابه‌جایی ترتیب نوشیدنی‌ها در پنل مدیریت
@app.route("/move/<int:id>/<direction>", methods=["POST"])
def move_drink(id, direction):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    drink = Drink.query.get_or_404(id)

    same_category_drinks = (
        Drink.query
        .filter_by(category=drink.category)
        .order_by(Drink.sort_order.asc(), Drink.id.asc())
        .all()
    )

    # اگر به هر دلیلی sort_orderها نامرتب بودند، اول مرتب‌شان می‌کنیم
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


# حذف نوشیدنی - با POST
@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    drink = Drink.query.get_or_404(id)
    category = drink.category

    # حذف عکس از Cloudinary
    delete_image_from_cloudinary(drink.image)

    db.session.delete(drink)
    db.session.commit()

    # بعد از حذف، ترتیب همان دسته‌بندی مرتب شود
    normalize_category_order(category)
    db.session.commit()

    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
