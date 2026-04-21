from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3

app = Flask(__name__)
app.secret_key = "secretkey"


def db():
    return sqlite3.connect("database.db")


# ================= DATABASE =================

conn = db()

conn.execute("""
CREATE TABLE IF NOT EXISTS users(
email TEXT PRIMARY KEY,
password TEXT
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS bookings(
email TEXT,
room TEXT,
date TEXT,
hours INTEGER,
total INTEGER,
method TEXT,
start_time INTEGER,
end_time INTEGER,
status TEXT DEFAULT 'Pending'
)
""")

# SAFE MIGRATION
try:
    conn.execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'Pending'")
except:
    pass


conn.execute("""
CREATE TABLE IF NOT EXISTS admin(
AdminID INTEGER PRIMARY KEY AUTOINCREMENT,
Name TEXT,
Email TEXT UNIQUE,
Password TEXT,
Role TEXT
)
""")


# ✅ NEW REVIEW TABLE (with room support)

conn.execute("""
CREATE TABLE IF NOT EXISTS reviews(
ReviewID INTEGER PRIMARY KEY AUTOINCREMENT,
Email TEXT,
Room TEXT,
Message TEXT,
Stars INTEGER DEFAULT 5,
Date TEXT DEFAULT CURRENT_TIMESTAMP
)
""")
# SAFE MIGRATION FOR OLD DATABASES

try:
    conn.execute("ALTER TABLE reviews ADD COLUMN Room TEXT")
except:
    pass
try:
    conn.execute("ALTER TABLE reviews ADD COLUMN Stars INTEGER DEFAULT 5")
except:
    pass
conn.commit()
conn.close()


# ================= ROOM DATA =================

ROOM_PRICE = {
"Private Room":20,
"Shared Room":8,
"Meeting Room":15,
"Training Room":25
}

ROOM_INFO = {
"Private Room":{"capacity":1,"total_rooms":3},
"Shared Room":{"capacity":6,"total_rooms":5},
"Meeting Room":{"capacity":10,"total_rooms":2},
"Training Room":{"capacity":20,"total_rooms":1}
}


# ================= LOGIN =================

@app.route("/", methods=["GET","POST"])
def login():

    if request.method == "POST":

        email=request.form["email"]
        password=request.form["password"]

        conn=db()
        cur=conn.cursor()

        cur.execute(
        "SELECT * FROM admin WHERE Email=? AND Password=?",
        (email,password)
        )

        admin=cur.fetchone()

        if admin:

            session["admin"]=admin[0]

            return redirect("/admin/dashboard")


        cur.execute(
        "SELECT * FROM users WHERE email=? AND password=?",
        (email,password)
        )

        user=cur.fetchone()

        if user:

            session["email"]=email

            return redirect("/home")


        return render_template(
        "login.html",
        error="Wrong email or password"
        )

    return render_template("login.html")


# ================= REGISTER =================

@app.route("/register", methods=["GET","POST"])
def register():

    if request.method=="POST":

        email=request.form["email"]
        password=request.form["password"]

        conn=db()
        cur=conn.cursor()

        try:

            cur.execute(
            "INSERT INTO users VALUES(?,?)",
            (email,password)
            )

            conn.commit()

            session["email"]=email

            return redirect("/home")

        except:

            return render_template(
            "register.html",
            error="Email already exists"
            )

    return render_template("register.html")


# ================= USER HOME =================

@app.route("/home")
def home():

    if "email" not in session:
        return redirect("/")

    conn=db()
    cur=conn.cursor()

    cur.execute("""
    SELECT rowid,room,date,hours,total,method,status
    FROM bookings
    WHERE email=?
    """,(session["email"],))

    history=cur.fetchall()

    return render_template(
    "home.html",
    history=history,
    email=session["email"]
    )
    
    
# ================= BOOKING =================
@app.route("/booking", methods=["GET","POST"])
def booking():

    if request.method=="POST":

        session["date"]=request.form["date"]
        session["start"]=int(request.form["start_time"])
        session["end"]=int(request.form["end_time"])
        session["hours"]=session["end"]-session["start"]

        return redirect("/rooms")

    return render_template("booking.html")


@app.route("/rooms", methods=["GET","POST"])
def rooms():

    if "date" not in session:
        return redirect("/booking")

    conn=db()
    cur=conn.cursor()

    availability={}

    for room in ROOM_INFO:

        cur.execute("""
        SELECT COUNT(*) FROM bookings
        WHERE room=? AND date=?
        AND NOT(end_time<=? OR start_time>=?)
        """,(room, session["date"], session["start"], session["end"]))

        overlap=cur.fetchone()[0]
        total=ROOM_INFO[room]["total_rooms"]

        availability[room]=total-overlap

    if request.method=="POST":

        selected=request.form["room"]

        session["room"]=selected
        session["total"]=ROOM_PRICE[selected]*session["hours"]

        return redirect("/payment")

    return render_template("rooms.html", availability=availability, info=ROOM_INFO)


@app.route("/payment", methods=["GET","POST"])
def payment():

    if request.method=="POST":

        conn=db()
        cur=conn.cursor()

        cur.execute("""
        INSERT INTO bookings
        (email,room,date,start_time,end_time,hours,total,method,status)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,(
        session["email"],
        session["room"],
        session["date"],
        session["start"],
        session["end"],
        session["hours"],
        session["total"],
        request.form["method"],
        "Pending"
        ))

        conn.commit()

        return redirect("/success")

    return render_template("payment.html", total=session["total"])


@app.route("/success")
def success():
    return render_template("success.html")    


# ================= RECEIPT =================
@app.route("/receipt/<int:id>")
def receipt(id):

    if "email" not in session:
        return redirect("/")

    conn = db()
    cur = conn.cursor()

    cur.execute("""
    SELECT room, date, start_time, end_time, hours, total, method, status
    FROM bookings
    WHERE rowid=? AND email=?
    """, (id, session["email"]))

    data = cur.fetchone()

    return render_template("receipt.html", data=data, id=id)


# ================= REVIEW SUBMIT =================

@app.route("/submit_review", methods=["POST"])
def submit_review():

    if "email" not in session:
        return redirect("/")

    room=request.form["room"]
    message=request.form["message"]
    stars=request.form["stars"]
    
    from datetime import datetime
    review_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn=db()
    cur=conn.cursor()

    cur.execute("""
   INSERT INTO reviews(Email,Room,Message,Stars,Date)
   VALUES(?,?,?,?,?)
   """,(session["email"],room,message,stars,review_date))
    conn.commit()

    return redirect("/home")


# ================= REVIEW SLIDESHOW DATA =================

@app.route("/reviews_data")
def reviews_data():

    if "email" not in session:
        return jsonify([])

    conn=db()
    cur=conn.cursor()

    cur.execute("""
    SELECT Email,Room,Message,Stars,
    strftime('%d-%m-%Y', Date)
    FROM reviews
    ORDER BY Date DESC
    """)

    rows=cur.fetchall()

    reviews=[]

    for r in rows:

        email=r[0]
        masked=email[:2] + "***@" + email.split("@")[1]

        reviews.append({
        "email":masked,
        "room":r[1],
        "message":r[2],
        "stars":r[3],
        "date": r[4] if r[4] else ""
        })

    return jsonify(reviews)


# ================= ADMIN MAILBOX =================

@app.route("/admin/mailbox")
def admin_mailbox():

    if "admin" not in session:
        return redirect("/")

    conn=db()
    cur=conn.cursor()

    cur.execute("""
    SELECT Email,Room,Message,Date
    FROM reviews
    ORDER BY Date DESC
    """)

    reviews=cur.fetchall()

    return render_template(
    "admin_mailbox.html",
    reviews=reviews
    )



# ================= POPULAR ROOMS DATA =================

@app.route("/popular_rooms_data")
def popular_rooms_data():

    if "email" not in session:
        return {}

    conn=db()
    cur=conn.cursor()

    cur.execute("""
    SELECT room,COUNT(*)
    FROM bookings
    WHERE strftime('%Y-%m',date)=strftime('%Y-%m','now')
    AND status='Approved'
    GROUP BY room
    """)

    data=cur.fetchall()

    labels=[]
    values=[]

    for row in data:

        labels.append(row[0])
        values.append(row[1])

    return {"labels":labels,"values":values}


# ================= ADMIN DASHBOARD =================

@app.route("/admin/dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect("/")

    conn=db()
    cur=conn.cursor()

    cur.execute("""
    SELECT rowid,email,room,date,hours,total,status
    FROM bookings
    """)

    bookings=cur.fetchall()

    # ================= INCOME CALCULATIONS =================

    # TODAY INCOME (Fixed to match standard HTML date formats)
    cur.execute("""
    SELECT IFNULL(SUM(total),0)
    FROM bookings
    WHERE date = strftime('%Y-%m-%d', 'now', 'localtime')
    AND status='Approved'
    """)
    today_income = cur.fetchone()[0]

    # MONTH INCOME
    cur.execute("""
    SELECT IFNULL(SUM(total),0)
    FROM bookings
    WHERE strftime('%Y-%m', date)=strftime('%Y-%m','now')
    AND status='Approved'
    """)
    month_income = cur.fetchone()[0]

    # TOTAL APPROVED INCOME
    cur.execute("""
    SELECT IFNULL(SUM(total),0)
    FROM bookings
    WHERE status='Approved'
    """)
    approved_income = cur.fetchone()[0]

    # TOTAL PENDING INCOME
    cur.execute("""
    SELECT IFNULL(SUM(total),0)
    FROM bookings
    WHERE status='Pending'
    """)
    pending_income = cur.fetchone()[0]

    # ================= END OF CALCULATIONS =================

    cur.execute("""
    SELECT room,COUNT(*)
    FROM bookings
    GROUP BY room
    """)

    stats=cur.fetchall()

    labels=[]
    values=[]

    for s in stats:

        labels.append(s[0])
        values.append(s[1])

    return render_template(
    "admin_dashboard.html",
    bookings=bookings,
    approved_income=approved_income,
    pending_income=pending_income,
    today_income=today_income,
    month_income=month_income,
    room_labels=labels,
    room_values=values
    )

# ================= ADMIN APPROVE =================

@app.route("/admin/approve/<int:id>")
def approve(id):

    conn=db()
    cur=conn.cursor()

    cur.execute(
    "UPDATE bookings SET status='Approved' WHERE rowid=?",
    (id,)
    )

    conn.commit()

    return redirect("/admin/dashboard")

# ================= ADMIN ROOM CONTROL =================
@app.route("/admin/rooms", methods=["GET","POST"])
def admin_rooms():

    if "admin" not in session:
        return redirect("/")

    if request.method == "POST":

        room = request.form["room"]
        total = int(request.form["total"])

        ROOM_INFO[room]["total_rooms"] = total

    availability = {}

    conn=db()
    cur=conn.cursor()

    for room in ROOM_INFO:

        cur.execute("""
        SELECT COUNT(*) FROM bookings
        WHERE room=? AND date=?
        """,(room, session.get("date","")))

        booked = cur.fetchone()[0]
        total = ROOM_INFO[room]["total_rooms"]

        availability[room] = total - booked

    return render_template("admin_rooms.html", info=ROOM_INFO, availability=availability)



# ================= LOGOUT =================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


@app.route("/admin/logout")
def admin_logout():

    session.pop("admin",None)

    return redirect("/")


# ================= CREATE ADMIN =================

@app.route("/create_admin")
def create_admin():

    conn=db()
    cur=conn.cursor()

    cur.execute(
    "SELECT * FROM admin WHERE Email=?",
    ("admin@gmail.com",)
    )

    if cur.fetchone():

        return "Admin already exists!"

    conn.execute("""
    INSERT INTO admin(Name,Email,Password,Role)
    VALUES('Admin','admin@gmail.com','1234','Manager')
    """)

    conn.commit()

    return "Admin created!"


if __name__=="__main__":
    app.run(debug=True)