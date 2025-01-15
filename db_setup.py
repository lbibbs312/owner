# db_setup.py

from flask_sqlalchemy import SQLAlchemy

# Create the SQLAlchemy object here, but do NOT bind it to an app yet
db = SQLAlchemy()


# EXAMPLE MODELS
# You can define your models here or in a separate `models.py`.
# For illustration, here's a basic User, Task, Announcement:

class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    role = db.Column(db.String(20), default="driver")

    # Relationship examples, etc.
    tasks = db.relationship("Task", backref="assigned_user", lazy="dynamic")


class Task(db.Model):
    __tablename__ = "task"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    # Example fields...
    is_hot = db.Column(db.Boolean, default=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)


class Announcement(db.Model):
    __tablename__ = "announcement"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
