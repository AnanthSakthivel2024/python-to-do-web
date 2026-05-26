from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from supabase import create_client
from dotenv import load_dotenv
import os
import hashlib
from datetime import datetime

today = datetime.today().strftime("%Y-%m-%d")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)


# ── Helpers ───────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """Simple SHA-256 hash for storing passwords."""
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    """Decorator: redirect to login if not logged in."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Auth Routes ───────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        # Look up user
        response = supabase.table("users") \
            .select("*") \
            .eq("username", username) \
            .execute()

        users = response.data
        if not users:
            flash("Username not found.", "danger")
            return redirect(url_for("login"))

        user = users[0]
        if user["password"] != hash_password(password):
            flash("Incorrect password.", "danger")
            return redirect(url_for("login"))

        # Save to session
        session["user_id"]  = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        confirm  = request.form["confirm"]

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        # Check if username already exists
        existing = supabase.table("users") \
            .select("id") \
            .eq("username", username) \
            .execute()

        if existing.data:
            flash("Username already taken.", "danger")
            return redirect(url_for("register"))

        # Insert new user
        supabase.table("users").insert({
            "username": username,
            "password": hash_password(password)
        }).execute()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ── Todo Routes ───────────────────────────────────────────────
@app.route("/home", methods=["GET", "POST"])
@login_required
def home():
    user_id = session["user_id"]

    if request.method == "POST":
        date = request.form["date"]
        task = request.form["task"].strip()

        if task:
            supabase.table("todo").insert({
                "user_id": user_id,
                "date":    date,
                "task":    task,
                "description": request.form["description"] or None,
                "priority": request.form["priority"],
                "due_time": request.form["due_time"] or None,
                "completed": "completed" in request.form
            }).execute()
            flash("Task added!", "success")

        return redirect(url_for("home"))

    # Fetch only this user's todos, newest first
    priority = request.args.get("priority")
    status = request.args.get("status")
    sort = request.args.get("sort", "newest")
    search = request.args.get("search")

    query = supabase.table("todo") \
        .select("*") \
        .eq("user_id", user_id)

    # Search filter
    if search:
        query = query.ilike("task", f"%{search}%")

    # Priority filter
    if priority:
        query = query.eq("priority", priority)

    # Completed filter
    if status is not None and status != "":
        if status.lower() == "true":
            query = query.eq("completed", True)
        elif status.lower() == "false":
            query = query.eq("completed", False)

    # Sorting
    if sort == "oldest":
        query = query.order("date", desc=False)

    else:
        query = query.order("date", desc=True)

    response = query.execute()

    todos = response.data
    resp = make_response(render_template("home.html", todos=todos, username=session["username"], today=today))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]        = "no-cache"
    resp.headers["Expires"]       = "0"
    return resp

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/delete/<int:todo_id>", methods=["POST"])
@login_required
def delete(todo_id):
    user_id = session["user_id"]

    # Only delete if it belongs to the logged-in user
    supabase.table("todo") \
        .delete() \
        .eq("id", todo_id) \
        .eq("user_id", user_id) \
        .execute()

    flash("Task deleted.", "info")
    return redirect(url_for("home"))

@app.route("/edit/<int:todo_id>", methods=["POST"])
@login_required
def edit(todo_id):
    user_id = session["user_id"]

    supabase.table("todo") \
        .update({
            "date": request.form["date"],
            "task": request.form["task"],
            "description": request.form["description"] or None,
            "priority": request.form["priority"],
            "due_time": request.form["due_time"] or None,
            "completed": "completed" in request.form
        }) \
        .eq("id", todo_id) \
        .eq("user_id", user_id) \
        .execute()

    flash("Task updated.", "info")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
