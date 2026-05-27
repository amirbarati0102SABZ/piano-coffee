from flask import Flask, render_template, request, redirect, session
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
import os


app = Flask(__name__)
app.secret_key = 'piano_coffee_secret'

# پوشه آپلود
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# تنظیمات MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '13521688'
app.config['MYSQL_DB'] = 'piano_coffee'

# اتصال
mysql = MySQL(app)

# صفحه اصلی
@app.route('/')

def home():

    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM drinks ORDER BY category")

    drinks = cur.fetchall()

    cur.close()

    return render_template("index.html", drinks=drinks)

# لاگین
@app.route('/login', methods=['GET', 'POST'])

def login():

    if request.method == 'POST':

        username = request.form['username']

        password = request.form['password']

        if username == 'admin' and password == '1234':

            session['admin'] = True

            return redirect('/admin')

    return render_template('login.html')

# پنل مدیریت
@app.route('/admin')

def admin():

    if 'admin' not in session:

        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM drinks")

    drinks = cur.fetchall()

    cur.close()

    return render_template('admin.html', drinks=drinks)
# افزودن نوشیدنی
@app.route('/add', methods=['GET', 'POST'])

def add():

    if request.method == 'POST':

        name = request.form['name']

        price = request.form['price']

        category = request.form['category']

        # گرفتن عکس
        image = request.files['image']

        # اسم امن فایل
        filename = secure_filename(image.filename)

        # ذخیره عکس
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # ذخیره در دیتابیس
        cur = mysql.connection.cursor()

        cur.execute(

            "INSERT INTO drinks(name, price, image, category) VALUES(%s,%s,%s,%s)",

            (name, price, filename, category)

        )

        mysql.connection.commit()

        cur.close()

        return redirect('/admin')

    return render_template('add.html')

# حذف نوشیدنی
@app.route('/delete/<int:id>')

def delete(id):

    cur = mysql.connection.cursor()

    cur.execute("DELETE FROM drinks WHERE id=%s", (id,))

    mysql.connection.commit()

    cur.close()

    return redirect('/admin')

# ویرایش نوشیدنی
@app.route('/edit/<int:id>', methods=['GET', 'POST'])

def edit(id):

    cur = mysql.connection.cursor()

    if request.method == 'POST':

        name = request.form['name']

        price = request.form['price']

        image = request.form['image']

        category = request.form['category']

        cur.execute("""

            UPDATE drinks

            SET name=%s,
                price=%s,
                image=%s,
                category=%s

            WHERE id=%s

        """, (name, price, image, category, id))

        mysql.connection.commit()

        cur.close()

        return redirect('/admin')

    cur.execute("SELECT * FROM drinks WHERE id=%s", (id,))

    drink = cur.fetchone()

    cur.close()

    return render_template('edit.html', drink=drink)
@app.route('/logout')

def logout():

    session.pop('admin', None)

    return redirect('/')

# اجرای پروژه
if __name__ == "__main__":

    app.run(debug=True)
