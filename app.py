from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# دیتابیس Render PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL",
    "postgresql://piano_user:H2nWMsj9VcObtKji8igAQ7DJLJBzlAwM@dpg-d8blnu8jo6nc73e633dg-a.virginia-postgres.render.com/piano_coffee"
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# جدول نوشیدنی‌ها
class Drink(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    price = db.Column(db.Integer)

    image = db.Column(db.String(200))

    category = db.Column(db.String(100))


# صفحه اصلی
@app.route('/')
def home():

    drinks = Drink.query.all()

    return render_template("index.html", drinks=drinks)


# ساخت جدول
with app.app_context():

    db.create_all()


# اجرای پروژه
if __name__ == "__main__":

    app.run(host="0.0.0.0", port=10000)