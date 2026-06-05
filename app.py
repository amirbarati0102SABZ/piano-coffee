from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
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

# حداکثر حجم آپلود: 5MB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# فرمت‌های مجاز عکس
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# دسته‌بندی‌های مجاز
ALLOWED_CATEGORIES = ["گرم", "سرد", "ماچا"]

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


# ساخت جدول‌ها
with app.app_context():
    db.create_all()


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


# صفحه اصلی مشتری
@app.route("/")
def home():
    drinks = Drink.query.order_by(Drink.id.desc()).all()
    return render_template("index.html", drinks=drinks)


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

    drinks = Drink.query.order_by(Drink.id.desc()).all()

    total_count = Drink.query.count()
    hot_count = Drink.query.filter_by(category="گرم").count()
    cold_count = Drink.query.filter_by(category="سرد").count()
    matcha_count = Drink.query.filter_by(category="ماچا").count()
    latest_drink = Drink.query.order_by(Drink.id.desc()).first()

    return render_template(
        "admin.html",
        drinks=drinks,
        total_count=total_count,
        hot_count=hot_count,
        cold_count=cold_count,
        matcha_count=matcha_count,
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
            return "آپلود عکس ناموفق بود یا فرمت عکس مجاز نیست. فقط png، jpg، jpeg و webp مجاز هستند."

        new_drink = Drink(
            name=name,
            price=price,
            image=image_url,
            category=category
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

        drink.name = name
        drink.price = price
        drink.category = category

        image_file = request.files.get("image")

        # اگر عکس جدید انتخاب شد
        if image_file and image_file.filename != "":
            image_url = upload_image_to_cloudinary(image_file)

            if not image_url:
                return "آپلود عکس ناموفق بود یا فرمت عکس مجاز نیست. فقط png، jpg، jpeg و webp مجاز هستند."

            # حذف عکس قبلی از Cloudinary
            delete_image_from_cloudinary(drink.image)

            drink.image = image_url

        db.session.commit()

        return redirect(url_for("admin"))

    return render_template("edit.html", drink=drink, categories=ALLOWED_CATEGORIES)


# حذف نوشیدنی - با POST
@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    drink = Drink.query.get_or_404(id)

    # حذف عکس از Cloudinary
    delete_image_from_cloudinary(drink.image)

    db.session.delete(drink)
    db.session.commit()

    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
