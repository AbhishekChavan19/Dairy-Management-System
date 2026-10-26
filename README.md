# Dairy Management System - Shetkari Dairy Farm, Jalgaon
Demo project built with Python + Flask + SQLite (HTML/CSS only on the front end).

## Login
Username: nikhilchavan
Password: dairy@123

## How to run
1. Install Python 3.9+ and check:  python --version
2. Open a terminal inside this folder (dairy_management).
3. (Optional but recommended) create a virtual environment:
     Windows:      python -m venv venv  then  venv\Scripts\activate
     Mac / Linux:  python3 -m venv venv  then  source venv/bin/activate
4. Install Flask:   pip install -r requirements.txt
5. Start the app:   python app.py        (Mac/Linux: python3 app.py)
6. Open in browser: http://127.0.0.1:5000

The database file (dairy.db) and demo data (10 farmers, 10 days of milk
collection, 8 products, sample bills) are created automatically on first run.

## Reset the demo data
Stop the app, delete dairy.db, and run  python app.py  again.

## Files
app.py            - all backend code (routes, database, rate calculation)
templates/        - HTML pages (Jinja2)
static/style.css  - all styling
requirements.txt  - only Flask is needed

## Rate formula
rate = fat x fat_rate + snf x snf_rate (+ buffalo bonus for buffalo milk)
amount = quantity x rate        (change the values in "Rate Settings")
