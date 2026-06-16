import os
import re
from datetime import datetime
from functools import wraps
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-before-deploy")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///sponsorshield.db").replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db = SQLAlchemy(app)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
ABUSIVE_WORDS = {"idiot", "stupid", "hate", "kill", "abuse", "trash", "scam", "fraud"}
CONTROVERSIAL_TOPICS = {"violence", "terror", "weapon", "drugs", "adult", "politics", "religion", "racism"}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    balance = db.Column(db.Float, default=0.0)
    total_earned = db.Column(db.Float, default=0.0)

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    platform = db.Column(db.String(60), nullable=False)
    required_keyword = db.Column(db.String(120), nullable=False)
    required_link = db.Column(db.String(180), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Escrow Funded")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submissions = db.relationship("Submission", backref="campaign", lazy=True)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaign.id"), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content_url = db.Column(db.String(500))
    video_file = db.Column(db.String(255))
    transcript = db.Column(db.Text)
    score = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="Pending Review")
    report = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please login first.", "error")
                return redirect(url_for("login"))
            if role and user.role != role:
                flash("You do not have permission for this page.", "error")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@app.context_processor
def inject_user():
    return {"user": current_user()}


def verify_submission(campaign, transcript, url):
    text = f"{transcript or ''} {url or ''}".lower()
    score = 0
    checks = []

    brand = campaign.required_keyword.lower()

    if brand in text:
        score += 20
        checks.append("Brand keyword found.")
    else:
        checks.append("Brand keyword missing.")

    phrase = f"sponsored by {brand}"
    if phrase in text:
        score += 25
        checks.append("Sponsor phrase found.")
    else:
        checks.append("Sponsor phrase missing.")

    if campaign.required_link.lower() in text:
        score += 15
        checks.append("Required link found.")
    else:
        checks.append("Required link missing.")

    hashtag = f"#{brand}partner"
    if hashtag in text:
        score += 15
        checks.append("Hashtag found.")
    else:
        checks.append("Hashtag missing.")

    abusive_found = [w for w in ABUSIVE_WORDS if w in text]
    controversial_found = [w for w in CONTROVERSIAL_TOPICS if w in text]

    if not abusive_found:
        score += 15
    else:
        checks.append("Abusive words: " + ", ".join(abusive_found))

    if not controversial_found:
        score += 10
    else:
        checks.append("Controversial topics: " + ", ".join(controversial_found))

    status = "Verified - Payout Released" if score >= 80 else "Needs Review"
    return score, status, "\n".join(checks)
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        if role not in {"brand", "creator"}:
            flash("Choose Brand or Creator.", "error")
        elif not EMAIL_RE.match(email):
            flash("Enter a valid email.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
        else:
            user = User(name=name or email.split("@")[0], email=email, password_hash=generate_password_hash(password), role=role)
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        user = User.query.filter_by(email=email).first()
        if not EMAIL_RE.match(email):
            flash("Enter a valid email.", "error")
        elif not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
        elif user.role != role:
            flash("Selected role does not match this account.", "error")
        else:
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required()
def dashboard():
    user = current_user()
    campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
    mine = []
    if user.role == "brand":
        mine = Campaign.query.filter_by(brand_id=user.id).order_by(Campaign.created_at.desc()).all()
    else:
        mine = Submission.query.filter_by(creator_id=user.id).order_by(Submission.created_at.desc()).all()
    return render_template("dashboard.html", campaigns=campaigns, mine=mine)

@app.route("/campaign/new", methods=["GET", "POST"])
@login_required("brand")
def new_campaign():
    if request.method == "POST":
        campaign = Campaign(
            brand_id=current_user().id,
            title=request.form.get("title", "").strip(),
            platform=request.form.get("platform", "YouTube"),
            required_keyword=request.form.get("required_keyword", "").strip(),
            required_link=request.form.get("required_link", "").strip(),
            amount=float(request.form.get("amount", 0) or 0),
        )
        db.session.add(campaign)
        db.session.commit()
        flash("Campaign created and escrow funded.", "success")
        return redirect(url_for("dashboard"))
    return render_template("campaign_form.html")

@app.route("/campaign/<int:campaign_id>/submit", methods=["GET", "POST"])
@login_required("creator")
def submit(campaign_id):
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        file = request.files.get("video")
        filename = None
        if file and file.filename:
            safe = secure_filename(file.filename)
            filename = f"{uuid4().hex}_{safe}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        transcript = request.form.get("transcript", "").strip()
        content_url = request.form.get("content_url", "").strip()
        score, status, report = verify_submission(campaign, transcript, content_url)
        submission = Submission(
            campaign_id=campaign.id,
            creator_id=current_user().id,
            content_url=content_url,
            video_file=filename,
            transcript=transcript,
            score=score,
            status=status,
            report=report,
        )
        campaign.status = status
        db.session.add(submission)
        db.session.commit()
        flash("Submission verified with Level-2 brand safety checks.", "success")
        return redirect(url_for("dashboard"))
    return render_template("submit.html", campaign=campaign)

@app.route("/submission/<int:submission_id>")
@login_required()
def submission_detail(submission_id):
    sub = db.session.get(Submission, submission_id)
    if not sub:
        flash("Submission not found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("submission_detail.html", sub=sub)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
