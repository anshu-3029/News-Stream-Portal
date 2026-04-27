from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    is_super_admin= db.Column(db.Boolean, default=False)  # only 1 super admin, can manage sub-admins
    is_active     = db.Column(db.Boolean, default=True)
    profile_pic   = db.Column(db.String(500), nullable=True)
    bio           = db.Column(db.String(300), nullable=True)
    joined_at     = db.Column(db.DateTime, default=datetime.utcnow)
    bookmarks     = db.relationship('Bookmark', backref='user', lazy=True, cascade='all, delete-orphan')

    def get_id(self):            return str(self.id)
    def set_password(self, p):   self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)


class News(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    title         = db.Column(db.String(200), nullable=False)
    description   = db.Column(db.Text)
    url           = db.Column(db.String(500))
    image_url     = db.Column(db.String(500))
    source        = db.Column(db.String(100))
    category      = db.Column(db.String(50))
    published_at  = db.Column(db.DateTime)
    is_featured   = db.Column(db.Boolean, default=False)
    is_admin_post = db.Column(db.Boolean, default=False)
    is_approved   = db.Column(db.Boolean, default=True)
    bookmarks     = db.relationship('Bookmark', backref='news', lazy=True, cascade='all, delete-orphan')


class Bookmark(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    news_id = db.Column(db.Integer, db.ForeignKey('news.id'), nullable=False)


class ContactQuery(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    email       = db.Column(db.String(120), nullable=False)
    subject     = db.Column(db.String(100), nullable=False)
    message     = db.Column(db.Text, nullable=False)
    submitted_at= db.Column(db.DateTime, default=datetime.utcnow)
    is_read     = db.Column(db.Boolean, default=False)
    is_resolved = db.Column(db.Boolean, default=False)
    admin_note  = db.Column(db.Text, nullable=True)       # internal note by admin
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # null if guest
    user        = db.relationship('User', backref='contact_queries', foreign_keys=[user_id])


class Comment(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    news_id      = db.Column(db.Integer, db.ForeignKey('news.id'), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content      = db.Column(db.Text, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved  = db.Column(db.Boolean, default=False)   # pending by default
    is_rejected  = db.Column(db.Boolean, default=False)
    parent_id    = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)  # for replies

    user    = db.relationship('User', backref='comments', foreign_keys=[user_id])
    news    = db.relationship('News', backref='comments', foreign_keys=[news_id])
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')