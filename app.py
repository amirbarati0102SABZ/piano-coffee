from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# Secret Key برای Session
app.secret_key = os.environ.get("SECRET_KEY", "piano-secret-key")

# مسیر آپلود عکس‌ها
UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# اگر پوشه uploads نبود بساز
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    image = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False)


# ساخت جدول‌ها
with app.app_context():
    db.create_all()


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

        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin_password = os.environ.get("ADMIN_PASSWORD", "1234")

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


# پنل مدیریت
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("login"))

    drinks = Drink.query.order_by(Drink.id.desc()).all()
    return render_template("admin.html", drinks=drinks)


# افزودن نوشیدنی
@app.route("/add", methods=["GET", "POST"])
def add():
    if not session.get("admin"):
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        category = request.form.get("category")
        image_file = request.files.get("image")

        if not name or not price or not category or not image_file:
            return "لطفاً همه فیلدها را کامل وارد کنید"

        filename = secure_filename(image_file.filename)

        if filename == "":
            return "لطفاً عکس انتخاب کنید"

        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(image_path)

        new_drink = Drink(
            name=name,
            price=int(price),
            image=filename,
            category=category
        )

        db.session.add(new_drink)
        db.session.commit()

        return redirect(url_for("admin"))

    return render_template("add.html")


# ویرایش نوشیدنی
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    if not session.get("admin"):
        return redirect(url_for("login"))

    drink = Drink.query.get_or_404(id)

    if request.method == "POST":
        drink.name = request.form.get("name")
        drink.price = int(request.form.get("price"))
        drink.category = request.form.get("category")

        image_file = request.files.get("image")

        # اگر عکس جدید انتخاب شد، جایگزین کن
        if image_file and image_file.filename != "":
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image_file.save(image_path)
            drink.image = filename

        db.session.commit()

        return redirect(url_for("admin"))

    return render_template("edit.html", drink=drink)


# حذف نوشیدنی
@app.route("/delete/<int:id>")
def delete(id):
    if not session.get("admin"):
        return redirect(url_for("login"))

    drink = Drink.query.get_or_404(id)

    db.session.delete(drink)
    db.session.commit()

    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
