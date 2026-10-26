"""
Dairy Management System - Shetkari Dairy Farm, Jalgaon
Simple demo project: Python + Flask + SQLite (no other libraries).

Run:  python app.py   ->   open http://127.0.0.1:5000
"""
import os
import random
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------
# STEP 1: App setup
# ---------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "dairy-demo-secret-key"          # needed for login session
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "dairy.db")      # database file (auto created)

LOW_STOCK_LIMIT = 20   # products below this stock show "Low"


# ---------------------------------------------------------------
# STEP 2: Database helpers
# ---------------------------------------------------------------
def get_db():
    """Open one database connection per request."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT DEFAULT 'admin'
);
CREATE TABLE IF NOT EXISTS farmers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    village TEXT,
    phone TEXT,
    animal_type TEXT,
    bank_account TEXT,
    joined_on TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS milk_collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id INTEGER NOT NULL REFERENCES farmers(id),
    coll_date TEXT NOT NULL,
    shift TEXT NOT NULL CHECK (shift IN ('Morning','Evening')),
    quantity REAL NOT NULL,
    fat REAL NOT NULL,
    snf REAL NOT NULL,
    rate REAL NOT NULL,
    amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id INTEGER NOT NULL REFERENCES farmers(id),
    period_from TEXT, period_to TEXT,
    gross_amount REAL, deduction REAL, net_amount REAL,
    paid_on TEXT, mode TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    unit TEXT, price REAL, stock REAL
);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, phone TEXT, address TEXT
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(id),
    sale_date TEXT, total REAL
);
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER REFERENCES sales(id),
    product_id INTEGER REFERENCES products(id),
    quantity REAL, price REAL, amount REAL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def calc_rate(fat, snf, animal_type, s):
    """Rate per litre = fat*fat_rate + snf*snf_rate (+ bonus for buffalo)."""
    rate = fat * s["fat_rate"] + snf * s["snf_rate"]
    if animal_type == "Buffalo":
        rate += s["buffalo_bonus"]
    return round(rate, 2)


def get_settings(db):
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    s = {r["key"]: r["value"] for r in rows}
    return {
        "dairy_name": s.get("dairy_name", "Dairy"),
        "fat_rate": float(s.get("fat_rate", 5)),
        "snf_rate": float(s.get("snf_rate", 2)),
        "buffalo_bonus": float(s.get("buffalo_bonus", 3)),
    }


# ---------------------------------------------------------------
# STEP 3: Create tables + demo data (runs only the first time)
# ---------------------------------------------------------------
def init_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)

    db.execute("UPDATE settings SET value=? WHERE key=? AND value=?",
               ("Shetkari Dairy Farm, Jalgaon", "dairy_name",
                "Demo Dairy Cooperative, Jalgaon"))

    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        db.commit()
        db.close()
        return  # already set up

    today = date.today()

    # --- admin login ---
    db.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
               ("nikhilchavan", generate_password_hash("dairy@123"),
                "Dairy Administrator", "admin"))

    # --- rate settings ---
    for k, v in [("dairy_name", "Shetkari Dairy Farm, Jalgaon"),
                 ("fat_rate", "5.00"), ("snf_rate", "2.00"), ("buffalo_bonus", "3.00")]:
        db.execute("INSERT INTO settings VALUES (?,?)", (k, v))

    # --- 10 farmers ---
    farmers = [
        ("F001", "Ramesh Patil", "Bambhori", "9822011101", "Cow", "2026-03-26"),
        ("F002", "Sunita Chaudhari", "Nashirabad", "9823022202", "Buffalo", "2026-04-04"),
        ("F003", "Dinesh Sonawane", "Khedi", "9860033303", "Cow", "2026-04-13"),
        ("F004", "Kavita Bhoite", "Pimprala", "9890044404", "Buffalo", "2026-04-22"),
        ("F005", "Prakash Wagh", "Mhasawad", "9765055505", "Cow", "2026-05-01"),
        ("F006", "Meena Koli", "Sunsgaon", "9921066606", "Buffalo", "2026-05-10"),
        ("F007", "Santosh Jadhav", "Bambhori", "9604077707", "Cow", "2026-05-19"),
        ("F008", "Anita Thakare", "Dhanora", "9370088808", "Cow", "2026-05-28"),
        ("F009", "Vilas Mahajan", "Khedi", "9766099909", "Buffalo", "2026-06-06"),
        ("F010", "Rajendra Borse", "Pal", "9850010010", "Cow", "2026-06-15"),
    ]
    for code, name, village, phone, animal, joined in farmers:
        db.execute("INSERT INTO farmers (code,name,village,phone,animal_type,joined_on,active) "
                   "VALUES (?,?,?,?,?,?,1)", (code, name, village, phone, animal, joined))

    # --- 8 products ---
    products = [
        ("Butter (500 g)", "Packet", 285, 36), ("Buttermilk", "Litre", 20, 70),
        ("Curd", "Kg", 80, 42), ("Full Cream Milk", "Litre", 66, 95),
        ("Ghee", "Kg", 640, 18), ("Paneer", "Kg", 360, 25),
        ("Sweet Lassi", "Piece", 25, 60), ("Toned Milk (Pouch)", "Litre", 54, 180),
    ]
    for p in products:
        db.execute("INSERT INTO products (name,unit,price,stock) VALUES (?,?,?,?)", p)

    # --- customers ---
    for c in [("Hotel Ananda", "9890111222", "Jalgaon"),
              ("Mrs. Deshmukh", "9890333444", "Jalgaon"),
              ("Shree Sweet Mart", "9890555666", "Jalgaon")]:
        db.execute("INSERT INTO customers (name,phone,address) VALUES (?,?,?)", c)

    # --- 10 days of milk collection (random but repeatable) ---
    s = {"fat_rate": 5.0, "snf_rate": 2.0, "buffalo_bonus": 3.0}
    random.seed(7)
    farmer_rows = db.execute("SELECT id, animal_type FROM farmers").fetchall()
    for d in range(9, -1, -1):
        day = (today - timedelta(days=d)).isoformat()
        for f in farmer_rows:
            for shift in ("Morning", "Evening"):
                if random.random() < 0.08:      # sometimes a farmer skips a shift
                    continue
                if f["animal_type"] == "Buffalo":
                    qty = round(random.uniform(12, 24), 1)
                    fat = round(random.uniform(6.4, 7.8), 1)
                    snf = round(random.uniform(8.9, 9.5), 1)
                else:
                    qty = round(random.uniform(14, 24), 1)
                    fat = round(random.uniform(3.4, 4.6), 1)
                    snf = round(random.uniform(8.1, 8.9), 1)
                rate = calc_rate(fat, snf, f["animal_type"], s)
                db.execute("INSERT INTO milk_collection "
                           "(farmer_id,coll_date,shift,quantity,fat,snf,rate,amount) "
                           "VALUES (?,?,?,?,?,?,?,?)",
                           (f["id"], day, shift, qty, fat, snf, rate, round(qty * rate, 2)))

    # --- 3 old payments ---
    p_from = (today - timedelta(days=19)).isoformat()
    p_to = (today - timedelta(days=10)).isoformat()
    paid_on = (today - timedelta(days=9)).isoformat()
    for fid, gross, ded, mode in [(3, 5480.75, 150, "Cash"), (2, 9215.00, 0, "Bank"),
                                  (1, 6820.50, 200, "Bank")]:
        db.execute("INSERT INTO payments (farmer_id,period_from,period_to,gross_amount,"
                   "deduction,net_amount,paid_on,mode) VALUES (?,?,?,?,?,?,?,?)",
                   (fid, p_from, p_to, gross, ded, gross - ded, paid_on, mode))

    # --- 4 old sales bills ---
    t, y = today.isoformat(), (today - timedelta(days=1)).isoformat()
    old_sales = [
        (3, t, [(6, 5), (3, 12.5)]),            # Shree Sweet Mart: paneer + curd
        (1, y, [(6, 5), (3, 10)]),              # Hotel Ananda
        (None, t, [(4, 5), (2, 2)]),            # walk-in
        (2, y, [(1, 1), (4, 5), (6, 1)]),       # Mrs. Deshmukh
    ]
    for cust, sdate, items in old_sales:
        cur = db.execute("INSERT INTO sales (customer_id,sale_date,total) VALUES (?,?,0)",
                         (cust, sdate))
        total = 0
        for pid, qty in items:
            price = db.execute("SELECT price FROM products WHERE id=?", (pid,)).fetchone()[0]
            amt = qty * price
            total += amt
            db.execute("INSERT INTO sale_items (sale_id,product_id,quantity,price,amount) "
                       "VALUES (?,?,?,?,?)", (cur.lastrowid, pid, qty, price, amt))
        db.execute("UPDATE sales SET total=? WHERE id=?", (total, cur.lastrowid))

    db.commit()
    db.close()


# ---------------------------------------------------------------
# STEP 4: Login protection + template helpers
# ---------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.template_filter("money")
def money(value):
    return "{:.2f}".format(value or 0)


@app.template_filter("num")
def num(value):
    """Show 18.0 as 18 and 14.5 as 14.5"""
    value = value or 0
    return str(int(value)) if float(value).is_integer() else str(round(value, 2))


@app.context_processor
def inject_common():
    if "user" in session:
        s = get_settings(get_db())
        return {"dairy_name": s["dairy_name"], "full_name": session.get("full_name")}
    return {}


# ---------------------------------------------------------------
# STEP 5: Login / Logout
# ---------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = user["username"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------
# STEP 6: Dashboard
# ---------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    today = date.today()
    t = today.isoformat()

    litres, payable = db.execute(
        "SELECT COALESCE(SUM(quantity),0), COALESCE(SUM(amount),0) "
        "FROM milk_collection WHERE coll_date=?", (t,)).fetchone()
    sales_today = db.execute(
        "SELECT COALESCE(SUM(total),0) FROM sales WHERE sale_date=?", (t,)).fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM farmers WHERE active=1").fetchone()[0]

    # last 7 days chart
    days = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        q = db.execute("SELECT COALESCE(SUM(quantity),0) FROM milk_collection WHERE coll_date=?",
                       (d.isoformat(),)).fetchone()[0]
        days.append({"label": d.strftime("%m-%d"), "litres": round(q)})
    biggest = max([d["litres"] for d in days] + [1])
    for d in days:
        d["height"] = int(d["litres"] / biggest * 100)

    low_stock = db.execute("SELECT * FROM products WHERE stock < ? ORDER BY stock",
                           (LOW_STOCK_LIMIT,)).fetchall()
    week_start = (today - timedelta(days=6)).isoformat()
    top = db.execute(
        "SELECT f.code, f.name, SUM(m.quantity) AS litres, SUM(m.amount) AS amount "
        "FROM milk_collection m JOIN farmers f ON f.id=m.farmer_id "
        "WHERE m.coll_date >= ? GROUP BY f.id ORDER BY litres DESC LIMIT 5",
        (week_start,)).fetchall()

    return render_template("dashboard.html", today=t, litres=litres, payable=payable,
                           sales_today=sales_today, active=active, days=days,
                           low_stock=low_stock, top=top)


# ---------------------------------------------------------------
# STEP 7: Farmers
# ---------------------------------------------------------------
def next_farmer_code(db):
    biggest = 0
    for r in db.execute("SELECT code FROM farmers").fetchall():
        digits = r["code"][1:]
        if digits.isdigit():
            biggest = max(biggest, int(digits))
    return "F%03d" % (biggest + 1)


@app.route("/farmers", methods=["GET", "POST"])
@login_required
def farmers():
    db = get_db()
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        name = request.form.get("name", "").strip()
        village = request.form.get("village", "").strip()
        phone = request.form.get("phone", "").strip()
        animal = request.form.get("animal_type", "Cow")
        bank = request.form.get("bank_account", "").strip()

        if not code or not name:
            flash("Farmer code and name are required.", "error")
        elif phone and not (phone.isdigit() and len(phone) == 10):
            flash("Mobile number must have exactly 10 digits.", "error")
        else:
            try:
                db.execute("INSERT INTO farmers (code,name,village,phone,animal_type,"
                           "bank_account,joined_on,active) VALUES (?,?,?,?,?,?,?,1)",
                           (code, name, village, phone, animal, bank, date.today().isoformat()))
                db.commit()
                flash("Farmer registered successfully.", "success")
            except sqlite3.IntegrityError:
                flash("Farmer code " + code + " already exists.", "error")
        return redirect(url_for("farmers"))

    rows = db.execute("SELECT * FROM farmers ORDER BY code").fetchall()
    return render_template("farmers.html", farmers=rows, next_code=next_farmer_code(db))


@app.route("/farmers/<int:farmer_id>/toggle", methods=["POST"])
@login_required
def toggle_farmer(farmer_id):
    db = get_db()
    db.execute("UPDATE farmers SET active = 1 - active WHERE id=?", (farmer_id,))
    db.commit()
    return redirect(url_for("farmers"))


# ---------------------------------------------------------------
# STEP 8: Milk collection
# ---------------------------------------------------------------
@app.route("/milk", methods=["GET", "POST"])
@login_required
def milk():
    db = get_db()
    s = get_settings(db)
    view_date = request.args.get("date", date.today().isoformat())

    if request.method == "POST":
        view_date = request.form.get("date", view_date)
        shift = request.form.get("shift", "Morning")
        try:
            farmer_id = int(request.form.get("farmer_id", 0))
            qty = float(request.form.get("quantity", ""))
            fat = float(request.form.get("fat", ""))
            snf = float(request.form.get("snf", ""))
        except ValueError:
            flash("Please enter valid numbers for farmer, quantity, fat and SNF.", "error")
            return redirect(url_for("milk", date=view_date))

        farmer = db.execute("SELECT * FROM farmers WHERE id=? AND active=1", (farmer_id,)).fetchone()
        if not farmer:
            flash("Please select a valid active farmer.", "error")
        elif qty <= 0:
            flash("Quantity must be greater than zero.", "error")
        elif not (0 < fat <= 15) or not (0 < snf <= 15):
            flash("Fat and SNF must be between 0 and 15.", "error")
        else:
            rate = calc_rate(fat, snf, farmer["animal_type"], s)
            amount = round(qty * rate, 2)
            db.execute("INSERT INTO milk_collection (farmer_id,coll_date,shift,quantity,fat,snf,"
                       "rate,amount) VALUES (?,?,?,?,?,?,?,?)",
                       (farmer_id, view_date, shift, qty, fat, snf, rate, amount))
            db.commit()
            flash("Saved: %s L from %s at Rs. %.2f/L = Rs. %.2f" %
                  (num(qty), farmer["name"], rate, amount), "success")
        return redirect(url_for("milk", date=view_date))

    farmers_list = db.execute("SELECT * FROM farmers WHERE active=1 ORDER BY code").fetchall()
    entries = db.execute(
        "SELECT m.*, f.code, f.name FROM milk_collection m JOIN farmers f ON f.id=m.farmer_id "
        "WHERE m.coll_date=? ORDER BY m.id DESC", (view_date,)).fetchall()
    total_qty = sum(e["quantity"] for e in entries)
    total_amt = sum(e["amount"] for e in entries)
    return render_template("milk.html", s=s, farmers=farmers_list, entries=entries,
                           view_date=view_date, total_qty=total_qty, total_amt=total_amt)


# ---------------------------------------------------------------
# STEP 9: Farmer payments (period-wise bills)
# ---------------------------------------------------------------
@app.route("/payments")
@login_required
def payments():
    db = get_db()
    today = date.today()
    date_from = request.args.get("date_from", (today - timedelta(days=9)).isoformat())
    date_to = request.args.get("date_to", today.isoformat())

    bills = db.execute(
        "SELECT f.id, f.code, f.name, SUM(m.quantity) AS litres, AVG(m.fat) AS avg_fat, "
        "AVG(m.snf) AS avg_snf, SUM(m.amount) AS gross "
        "FROM milk_collection m JOIN farmers f ON f.id=m.farmer_id "
        "WHERE m.coll_date BETWEEN ? AND ? GROUP BY f.id ORDER BY f.code",
        (date_from, date_to)).fetchall()

    rows = []
    for b in bills:
        paid = db.execute("SELECT * FROM payments WHERE farmer_id=? AND period_from=? AND period_to=?",
                          (b["id"], date_from, date_to)).fetchone()
        rows.append({"bill": b, "paid": paid})

    recent = db.execute(
        "SELECT p.*, f.code, f.name FROM payments p JOIN farmers f ON f.id=p.farmer_id "
        "ORDER BY p.id DESC LIMIT 10").fetchall()
    return render_template("payments.html", rows=rows, recent=recent,
                           date_from=date_from, date_to=date_to)


@app.route("/payments/pay", methods=["POST"])
@login_required
def pay():
    db = get_db()
    farmer_id = int(request.form["farmer_id"])
    date_from = request.form["date_from"]
    date_to = request.form["date_to"]
    mode = request.form.get("mode", "Cash")
    try:
        deduction = float(request.form.get("deduction") or 0)
    except ValueError:
        deduction = -1

    # gross amount is calculated again from the database (not trusted from the form)
    gross = db.execute("SELECT COALESCE(SUM(amount),0) FROM milk_collection "
                       "WHERE farmer_id=? AND coll_date BETWEEN ? AND ?",
                       (farmer_id, date_from, date_to)).fetchone()[0]
    already = db.execute("SELECT id FROM payments WHERE farmer_id=? AND period_from=? AND period_to=?",
                         (farmer_id, date_from, date_to)).fetchone()
    farmer = db.execute("SELECT name FROM farmers WHERE id=?", (farmer_id,)).fetchone()

    if already:
        flash("This bill is already paid.", "error")
    elif deduction < 0 or deduction > gross:
        flash("Deduction must be between 0 and the gross amount.", "error")
    else:
        net = round(gross - deduction, 2)
        db.execute("INSERT INTO payments (farmer_id,period_from,period_to,gross_amount,deduction,"
                   "net_amount,paid_on,mode) VALUES (?,?,?,?,?,?,?,?)",
                   (farmer_id, date_from, date_to, round(gross, 2), deduction, net,
                    date.today().isoformat(), mode))
        db.commit()
        flash("Payment recorded for %s. Net paid Rs. %.2f (%s)" % (farmer["name"], net, mode), "success")
    return redirect(url_for("payments", date_from=date_from, date_to=date_to))


# ---------------------------------------------------------------
# STEP 10: Products & stock
# ---------------------------------------------------------------
@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "Litre")
        try:
            price = float(request.form.get("price", ""))
            stock = float(request.form.get("stock") or 0)
        except ValueError:
            flash("Price and stock must be numbers.", "error")
            return redirect(url_for("products"))
        if not name or price <= 0 or stock < 0:
            flash("Enter a product name and a valid price.", "error")
        else:
            try:
                db.execute("INSERT INTO products (name,unit,price,stock) VALUES (?,?,?,?)",
                           (name, unit, price, stock))
                db.commit()
                flash("Product added successfully.", "success")
            except sqlite3.IntegrityError:
                flash("Product already exists.", "error")
        return redirect(url_for("products"))

    rows = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return render_template("products.html", products=rows, low=LOW_STOCK_LIMIT)


@app.route("/products/<int:product_id>/add-stock", methods=["POST"])
@login_required
def add_stock(product_id):
    db = get_db()
    try:
        qty = float(request.form.get("qty", ""))
    except ValueError:
        qty = 0
    if qty <= 0:
        flash("Enter a positive quantity to add.", "error")
    else:
        db.execute("UPDATE products SET stock = stock + ? WHERE id=?", (qty, product_id))
        db.commit()
        flash("Stock updated.", "success")
    return redirect(url_for("products"))


# ---------------------------------------------------------------
# STEP 11: Sales & billing
# ---------------------------------------------------------------
@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    db = get_db()

    if request.method == "POST":
        customer_id = request.form.get("customer_id") or None

        # collect up to 3 product lines
        lines = []
        for i in (1, 2, 3):
            pid = request.form.get("product_%d" % i)
            qty_text = request.form.get("qty_%d" % i, "").strip()
            if pid and qty_text:
                try:
                    qty = float(qty_text)
                except ValueError:
                    qty = 0
                lines.append((int(pid), qty))

        error = None
        if not lines:
            error = "Select at least one product and quantity."
        checked = []
        total = 0
        for pid, qty in lines:
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if qty <= 0:
                error = "Quantity must be greater than zero."
            elif p["stock"] < qty:
                error = "Insufficient stock for %s (available %s)." % (p["name"], num(p["stock"]))
            else:
                amount = round(qty * p["price"], 2)
                total += amount
                checked.append((p, qty, amount))

        if error:
            flash(error, "error")
        else:
            cur = db.execute("INSERT INTO sales (customer_id,sale_date,total) VALUES (?,?,?)",
                             (customer_id, date.today().isoformat(), total))
            for p, qty, amount in checked:
                db.execute("INSERT INTO sale_items (sale_id,product_id,quantity,price,amount) "
                           "VALUES (?,?,?,?,?)", (cur.lastrowid, p["id"], qty, p["price"], amount))
                db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, p["id"]))
            db.commit()    # sale + stock reduction saved together
            flash("Bill #%d generated. Total Rs. %.2f" % (cur.lastrowid, total), "success")
        return redirect(url_for("sales"))

    customers = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
    prods = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    recent = db.execute(
        "SELECT s.*, c.name AS customer FROM sales s LEFT JOIN customers c ON c.id=s.customer_id "
        "ORDER BY s.id DESC LIMIT 10").fetchall()
    return render_template("sales.html", customers=customers, products=prods, recent=recent)


@app.route("/sales/<int:sale_id>")
@login_required
def bill(sale_id):
    db = get_db()
    sale = db.execute("SELECT s.*, c.name AS customer, c.phone, c.address FROM sales s "
                      "LEFT JOIN customers c ON c.id=s.customer_id WHERE s.id=?", (sale_id,)).fetchone()
    if not sale:
        return redirect(url_for("sales"))
    items = db.execute("SELECT i.*, p.name, p.unit FROM sale_items i JOIN products p "
                       "ON p.id=i.product_id WHERE i.sale_id=?", (sale_id,)).fetchall()
    return render_template("bill.html", sale=sale, items=items)


# ---------------------------------------------------------------
# STEP 12: Reports
# ---------------------------------------------------------------
@app.route("/reports")
@login_required
def reports():
    db = get_db()
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    like = month + "%"

    litres, cost, days = db.execute(
        "SELECT COALESCE(SUM(quantity),0), COALESCE(SUM(amount),0), COUNT(DISTINCT coll_date) "
        "FROM milk_collection WHERE coll_date LIKE ?", (like,)).fetchone()
    product_sales = db.execute("SELECT COALESCE(SUM(total),0) FROM sales WHERE sale_date LIKE ?",
                               (like,)).fetchone()[0]

    daily = db.execute(
        "SELECT coll_date, COUNT(*) AS entries, SUM(quantity) AS litres, AVG(fat) AS avg_fat, "
        "SUM(amount) AS amount FROM milk_collection WHERE coll_date LIKE ? "
        "GROUP BY coll_date ORDER BY coll_date", (like,)).fetchall()
    by_farmer = db.execute(
        "SELECT f.code, f.name, f.village, SUM(m.quantity) AS litres, SUM(m.amount) AS amount "
        "FROM milk_collection m JOIN farmers f ON f.id=m.farmer_id WHERE m.coll_date LIKE ? "
        "GROUP BY f.id ORDER BY amount DESC", (like,)).fetchall()
    return render_template("reports.html", month=month, litres=litres, cost=cost, days=days,
                           product_sales=product_sales, daily=daily, by_farmer=by_farmer)


# ---------------------------------------------------------------
# STEP 13: Rate settings
# ---------------------------------------------------------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db = get_db()
    if request.method == "POST":
        try:
            fat = float(request.form["fat_rate"])
            snf = float(request.form["snf_rate"])
            bonus = float(request.form["buffalo_bonus"])
            name = request.form.get("dairy_name", "").strip() or "Dairy"
            if min(fat, snf, bonus) < 0:
                raise ValueError
        except ValueError:
            flash("Rates must be valid positive numbers.", "error")
            return redirect(url_for("settings"))
        for k, v in [("dairy_name", name), ("fat_rate", fat), ("snf_rate", snf),
                     ("buffalo_bonus", bonus)]:
            db.execute("UPDATE settings SET value=? WHERE key=?", (str(v), k))
        db.commit()
        flash("Settings saved. New rates apply to new milk entries.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", s=get_settings(db))


# ---------------------------------------------------------------
# STEP 14: Start the app
# ---------------------------------------------------------------
init_db()

if __name__ == "__main__":
    app.run(debug=True)
