from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
import requests
import os
from config import Config
from database import db, User, News, Bookmark, ContactQuery, Comment

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to read the full article.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

NEWS_API_URL = "https://newsapi.org/v2"
NEWS_API_KEY = 'ca0c0863546c417bab52b918bdcf6eb1'
CATEGORIES   = ['general','technology','sports','business','entertainment','health','science']


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def get_live_news(category='general', page_size=20):
    if not NEWS_API_KEY:
        return []
    try:
        url    = f"{NEWS_API_URL}/top-headlines"
        params = {'country':'us','category':category,'apiKey':NEWS_API_KEY,'pageSize':page_size}
        resp   = requests.get(url, params=params, timeout=8)
        return resp.json().get('articles', [])
    except Exception as e:
        print(f"[NewsAPI] {e}")
        return []


def ai_summary(text, max_length=200):
    if not text or len(text) < 50:
        return (text[:max_length] + '...') if text else 'Summary not available.'
    sentences = [s.strip() for s in text.replace('\n', ' ').split('. ') if s.strip()]
    summary   = '. '.join(sentences[:3])
    return (summary[:max_length] + '...') if len(summary) > max_length else summary


def get_user_bookmarks():
    if current_user.is_authenticated:
        return [b.news_id for b in current_user.bookmarks]
    return []


def require_admin():
    # Admin OR super-admin can access
    if not current_user.is_admin:
        abort(403)

def require_super_admin():
    # Only the super-admin can access
    if not current_user.is_super_admin:
        flash('This section is restricted to the Super Admin only.', 'danger')
        abort(403)


@app.context_processor
def inject_admin_globals():
    if current_user.is_authenticated and current_user.is_admin:
        result = {}
        if current_user.is_super_admin:
            try:
                result['unread_count'] = ContactQuery.query.filter_by(is_read=False).count()
            except Exception:
                result['unread_count'] = 0
        else:
            result['unread_count'] = 0
        # All admins see pending comment count
        try:
            result['pending_comments'] = Comment.query.filter_by(is_approved=False, is_rejected=False).count()
        except Exception:
            result['pending_comments'] = 0
        return result
    return {}


def save_api_articles(articles, category):
    """Persist API articles to DB (unapproved by default if approval mode on)."""
    for article in articles:
        if not article.get('url') or not article.get('title'):
            continue
        existing = News.query.filter_by(url=article['url']).first()
        try:
            pub_at = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))
        except Exception:
            pub_at = datetime.utcnow()
        if not existing:
            db.session.add(News(
                title=article['title'],
                description=article.get('description') or '',
                url=article['url'],
                image_url=article.get('urlToImage'),
                source=article['source']['name'],
                category=category,
                published_at=pub_at,
                is_admin_post=False,
                is_approved=True       # auto-approved; admin can reject later
            ))
        else:
            existing.title       = article['title']
            existing.description = article.get('description') or ''
            existing.image_url   = article.get('urlToImage')
    db.session.commit()


# ─────────────────────────────────────────────────────────────
#  PUBLIC ROUTES
# ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    category = request.args.get('category', 'general')
    page     = request.args.get('page', 1, type=int)

    # Fetch & cache API news
    try:
        articles = get_live_news(category)
        save_api_articles(articles, category)
    except Exception as e:
        print(f"[index] {e}")
        db.session.rollback()

    # Hybrid feed: approved API news + admin posts, newest first
    per_page   = 12
    news_items = News.query\
        .filter_by(category=category, is_approved=True)\
        .order_by(News.is_admin_post.desc(), News.published_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    # Trending: featured first, then newest
    trending = News.query.filter_by(is_featured=True, is_approved=True)\
                         .order_by(News.published_at.desc()).limit(5).all()
    if not trending:
        trending = News.query.filter_by(is_approved=True)\
                             .order_by(News.published_at.desc()).limit(5).all()

    recent = News.query.filter_by(is_approved=True)\
                       .order_by(News.published_at.desc()).limit(8).all()

    return render_template('index.html',
                           news=news_items.items,
                           pagination=news_items,
                           categories=CATEGORIES,
                           current_category=category,
                           bookmarks=get_user_bookmarks(),
                           trending=trending,
                           recent=recent)


@app.route('/news/<int:news_id>')
@login_required
def news_detail(news_id):
    news         = db.get_or_404(News, news_id)
    news.summary = ai_summary(news.description or news.title)
    # Approved top-level comments only, newest first
    comments = Comment.query.filter_by(
        news_id=news_id, is_approved=True, is_rejected=False, parent_id=None
    ).order_by(Comment.submitted_at.desc()).all()
    return render_template('news-detail.html', news=news, comments=comments)


@app.route('/news/<int:news_id>/comment', methods=['POST'])
@login_required
def add_comment(news_id):
    db.get_or_404(News, news_id)
    content   = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id', None, type=int)

    if not content or len(content) < 3:
        flash('Comment must be at least 3 characters.', 'danger')
        return redirect(url_for('news_detail', news_id=news_id))
    if len(content) > 1000:
        flash('Comment must be under 1000 characters.', 'danger')
        return redirect(url_for('news_detail', news_id=news_id))

    comment = Comment(
        news_id=news_id,
        user_id=current_user.id,
        content=content,
        parent_id=parent_id,
        is_approved=False,
        is_rejected=False
    )
    db.session.add(comment)
    db.session.commit()
    flash('Comment submitted! It will appear after admin approval.', 'success')
    return redirect(url_for('news_detail', news_id=news_id))


@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    news_id = comment.news_id
    # Only author or admin can delete
    if comment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    flash('Comment deleted.', 'info')
    return redirect(url_for('news_detail', news_id=news_id))


@app.route('/bookmark/<int:news_id>', methods=['POST'])
@login_required
def bookmark_news(news_id):
    db.get_or_404(News, news_id)
    bookmark = Bookmark.query.filter_by(user_id=current_user.id, news_id=news_id).first()
    if bookmark:
        db.session.delete(bookmark)
        flash('Removed from bookmarks.', 'info')
    else:
        db.session.add(Bookmark(user_id=current_user.id, news_id=news_id))
        flash('Bookmarked!', 'success')
    db.session.commit()
    return redirect(request.referrer or url_for('index'))


# ─────────────────────────────────────────────────────────────
#  USER PAGES
# ─────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('user/dashboard.html', bookmarks=current_user.bookmarks)

@app.route('/about')
def about():
    return render_template('user/about.html')

@app.route('/contact', methods=['GET','POST'])
def contact():
    if request.method == 'POST':
        name    = request.form.get('name','').strip()
        email   = request.form.get('email','').strip()
        subject = request.form.get('subject','General Inquiry').strip()
        message = request.form.get('message','').strip()

        if not name or not email or not message:
            flash('Please fill in all required fields.', 'danger')
            return render_template('user/contact.html')

        query = ContactQuery(
            name=name, email=email,
            subject=subject, message=message,
            user_id=current_user.id if current_user.is_authenticated else None
        )
        db.session.add(query)
        db.session.commit()
        flash('Your message has been sent! We\'ll get back to you within 24 hours.', 'success')
        return redirect(url_for('contact'))

    return render_template('user/contact.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin') if current_user.is_admin else url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            if user.is_admin:
                # Admins must use the admin login page
                flash('Please use the Admin Login portal.', 'warning')
                return redirect(url_for('admin_login'))
            if not user.is_active:
                flash('Your account has been deactivated.', 'danger')
                return render_template('login.html')
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('index'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already taken.', 'danger')
            return render_template('register.html')
        user = User(username=request.form['username'], email=request.form['email'])
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        flash('Account created! Please sign in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    was_admin = current_user.is_admin
    logout_user()
    return redirect(url_for('admin_login') if was_admin else url_for('index'))

@app.route('/profile/edit', methods=['GET','POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_info':
            new_u = request.form.get('username','').strip()
            new_e = request.form.get('email','').strip()
            new_b = request.form.get('bio','').strip()
            if new_u != current_user.username:
                if User.query.filter_by(username=new_u).first():
                    flash('Username already taken.', 'danger')
                    return redirect(url_for('edit_profile'))
                current_user.username = new_u
            if new_e != current_user.email:
                if User.query.filter_by(email=new_e).first():
                    flash('Email already in use.', 'danger')
                    return redirect(url_for('edit_profile'))
                current_user.email = new_e
            current_user.bio = new_b
            db.session.commit()
            flash('Profile updated!', 'success')
        elif action == 'change_password':
            cur = request.form.get('current_password','')
            new = request.form.get('new_password','')
            con = request.form.get('confirm_password','')
            if not current_user.check_password(cur):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('edit_profile'))
            if len(new) < 6:
                flash('Password must be at least 6 characters.', 'danger')
                return redirect(url_for('edit_profile'))
            if new != con:
                flash('Passwords do not match.', 'danger')
                return redirect(url_for('edit_profile'))
            current_user.set_password(new)
            db.session.commit()
            flash('Password changed!', 'success')
        elif action == 'update_avatar':
            url = request.form.get('avatar_url','').strip()
            if url:
                current_user.profile_pic = url
                db.session.commit()
                flash('Profile picture updated!', 'success')
            else:
                flash('Please provide an image URL.', 'danger')
        return redirect(url_for('edit_profile'))
    return render_template('user/edit_profile.html')


# ─────────────────────────────────────────────────────────────
#  ADMIN ROUTES
# ─────────────────────────────────────────────────────────────


@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            if not user.is_admin:
                flash('Access denied. Not an admin account.', 'danger')
                return render_template('admin/login.html')
            if not user.is_active:
                flash('This admin account has been deactivated.', 'danger')
                return render_template('admin/login.html')
            login_user(user)
            flash(f'Welcome, Admin {user.username}!', 'success')
            return redirect(url_for('admin'))
        flash('Invalid admin credentials.', 'danger')
    return render_template('admin/login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('Logged out from admin panel.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin')
@login_required
def admin():
    require_admin()
    # Stats
    total_news    = News.query.count()
    admin_posts   = News.query.filter_by(is_admin_post=True).count()
    api_news      = News.query.filter_by(is_admin_post=False).count()
    pending       = News.query.filter_by(is_approved=False).count()
    total_users   = User.query.count()
    total_bmarks  = Bookmark.query.count()
    total_queries = ContactQuery.query.count()
    unread_q      = ContactQuery.query.filter_by(is_read=False).count()
    total_comments= Comment.query.count()
    pending_cmnts = Comment.query.filter_by(is_approved=False, is_rejected=False).count()

    # Filters
    filter_cat    = request.args.get('category', 'all')
    filter_type   = request.args.get('type', 'all')   # all | admin | api
    filter_status = request.args.get('status', 'all') # all | approved | rejected
    page          = request.args.get('page', 1, type=int)

    q = News.query
    if filter_cat    != 'all': q = q.filter_by(category=filter_cat)
    if filter_type   == 'admin': q = q.filter_by(is_admin_post=True)
    if filter_type   == 'api':   q = q.filter_by(is_admin_post=False)
    if filter_status == 'approved': q = q.filter_by(is_approved=True)
    if filter_status == 'rejected': q = q.filter_by(is_approved=False)

    news_pages = q.order_by(News.published_at.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template('admin/dashboard.html',
        news=news_pages.items,
        pagination=news_pages,
        stats=dict(total=total_news, admin=admin_posts, api=api_news,
                   pending=pending, users=total_users, bookmarks=total_bmarks,
                   queries=total_queries, unread_queries=unread_q,
                   comments=total_comments, pending_comments=pending_cmnts),
        categories=CATEGORIES,
        filter_cat=filter_cat, filter_type=filter_type, filter_status=filter_status)


@app.route('/admin/add', methods=['GET','POST'])
@login_required
def admin_add_news():
    require_admin()
    if request.method == 'POST':
        db.session.add(News(
            title        = request.form['title'],
            description  = request.form.get('description',''),
            url          = request.form.get('url',''),
            image_url    = request.form.get('image_url') or None,
            source       = request.form.get('source','NewsStream Editorial'),
            category     = request.form.get('category','general'),
            published_at = datetime.utcnow(),
            is_admin_post= True,
            is_approved  = True,
            is_featured  = bool(request.form.get('is_featured'))
        ))
        db.session.commit()
        flash('Article published successfully!', 'success')
        return redirect(url_for('admin'))
    return render_template('admin/add_news.html', categories=CATEGORIES)


@app.route('/admin/edit/<int:news_id>', methods=['GET','POST'])
@login_required
def admin_edit_news(news_id):
    require_admin()
    news = db.get_or_404(News, news_id)
    if request.method == 'POST':
        news.title       = request.form['title']
        news.description = request.form.get('description','')
        news.url         = request.form.get('url','')
        news.image_url   = request.form.get('image_url') or None
        news.source      = request.form.get('source', news.source)
        news.category    = request.form.get('category', news.category)
        news.is_featured = bool(request.form.get('is_featured'))
        db.session.commit()
        flash('Article updated!', 'success')
        return redirect(url_for('admin'))
    return render_template('admin/edit_news.html', news=news, categories=CATEGORIES)


@app.route('/admin/delete/<int:news_id>', methods=['POST'])
@login_required
def admin_delete_news(news_id):
    require_admin()
    news = db.get_or_404(News, news_id)
    db.session.delete(news)
    db.session.commit()
    flash('Article deleted.', 'info')
    return redirect(request.referrer or url_for('admin'))


@app.route('/admin/approve/<int:news_id>', methods=['POST'])
@login_required
def admin_approve_news(news_id):
    require_admin()
    news = db.get_or_404(News, news_id)
    news.is_approved = True
    db.session.commit()
    flash(f'"{news.title[:50]}" approved.', 'success')
    return redirect(request.referrer or url_for('admin'))


@app.route('/admin/reject/<int:news_id>', methods=['POST'])
@login_required
def admin_reject_news(news_id):
    require_admin()
    news = db.get_or_404(News, news_id)
    news.is_approved = False
    db.session.commit()
    flash(f'"{news.title[:50]}" rejected — hidden from feed.', 'info')
    return redirect(request.referrer or url_for('admin'))


@app.route('/admin/feature/<int:news_id>', methods=['POST'])
@login_required
def admin_feature_news(news_id):
    require_admin()
    news = db.get_or_404(News, news_id)
    news.is_featured = not news.is_featured
    db.session.commit()
    return redirect(request.referrer or url_for('admin'))


@app.route('/admin/bulk', methods=['POST'])
@login_required
def admin_bulk_action():
    require_admin()
    action   = request.form.get('bulk_action')
    news_ids = request.form.getlist('selected_ids')
    if not news_ids:
        flash('No articles selected.', 'warning')
        return redirect(url_for('admin'))
    count = 0
    for nid in news_ids:
        news = db.session.get(News, int(nid))
        if not news: continue
        if action == 'approve':  news.is_approved = True;  count += 1
        if action == 'reject':   news.is_approved = False; count += 1
        if action == 'feature':  news.is_featured = True;  count += 1
        if action == 'unfeature':news.is_featured = False; count += 1
        if action == 'delete':   db.session.delete(news);  count += 1
    db.session.commit()
    flash(f'Bulk action "{action}" applied to {count} articles.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/fetch-api', methods=['POST'])
@login_required
def admin_fetch_api():
    """Manually trigger API fetch for a specific category."""
    require_admin()
    category = request.form.get('category', 'general')
    articles = get_live_news(category, page_size=20)
    saved = 0
    for article in articles:
        if not article.get('url') or not article.get('title'): continue
        if not News.query.filter_by(url=article['url']).first():
            try:
                pub_at = datetime.fromisoformat(article['publishedAt'].replace('Z','+00:00'))
            except:
                pub_at = datetime.utcnow()
            db.session.add(News(
                title=article['title'], description=article.get('description') or '',
                url=article['url'], image_url=article.get('urlToImage'),
                source=article['source']['name'], category=category,
                published_at=pub_at, is_admin_post=False, is_approved=True
            ))
            saved += 1
    db.session.commit()
    flash(f'Fetched {len(articles)} articles from API, {saved} new saved for "{category}".', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users')
@login_required
def admin_users():
    require_admin()
    users = User.query.order_by(User.id).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
@login_required
def admin_toggle_user(user_id):
    require_admin()
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You can't deactivate yourself.", 'danger')
        return redirect(url_for('admin_users'))
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'User "{user.username}" {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin_users'))


# ─────────────────────────────────────────────────────────────
#  API + ERRORS
# ─────────────────────────────────────────────────────────────


@app.route('/admin/admins')
@login_required
def admin_manage_admins():
    if not current_user.is_super_admin:
        flash('Only the Super Admin can manage admins.', 'danger')
        return redirect(url_for('admin'))
    admins = User.query.filter_by(is_admin=True).order_by(User.id).all()
    return render_template('admin/manage_admins.html', admins=admins)


@app.route('/admin/admins/add', methods=['POST'])
@login_required
def admin_add_subadmin():
    if not current_user.is_super_admin:
        abort(403)
    username = request.form.get('username','').strip()
    email    = request.form.get('email','').strip()
    password = request.form.get('password','').strip()

    if not username or not email or not password:
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin_manage_admins'))
    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'danger')
        return redirect(url_for('admin_manage_admins'))
    if User.query.filter_by(email=email).first():
        flash(f'Email already registered.', 'danger')
        return redirect(url_for('admin_manage_admins'))

    sub = User(username=username, email=email, is_admin=True, is_super_admin=False)
    sub.set_password(password)
    db.session.add(sub)
    db.session.commit()
    flash(f'Sub-admin "{username}" created successfully!', 'success')
    return redirect(url_for('admin_manage_admins'))


@app.route('/admin/admins/remove/<int:user_id>', methods=['POST'])
@login_required
def admin_remove_subadmin(user_id):
    if not current_user.is_super_admin:
        abort(403)
    user = db.get_or_404(User, user_id)
    if user.is_super_admin:
        flash('Cannot remove the Super Admin.', 'danger')
        return redirect(url_for('admin_manage_admins'))
    if user.id == current_user.id:
        flash("You can't remove yourself.", 'danger')
        return redirect(url_for('admin_manage_admins'))
    # Demote to regular user rather than delete
    action = request.form.get('action', 'demote')
    if action == 'delete':
        db.session.delete(user)
        flash(f'Admin "{user.username}" deleted permanently.', 'info')
    else:
        user.is_admin = False
        flash(f'"{user.username}" demoted to regular user.', 'info')
    db.session.commit()
    return redirect(url_for('admin_manage_admins'))


@app.route('/admin/admins/toggle/<int:user_id>', methods=['POST'])
@login_required
def admin_toggle_subadmin(user_id):
    if not current_user.is_super_admin:
        abort(403)
    user = db.get_or_404(User, user_id)
    if user.is_super_admin:
        flash('Cannot deactivate Super Admin.', 'danger')
        return redirect(url_for('admin_manage_admins'))
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'Admin "{user.username}" {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin_manage_admins'))


@app.route('/admin/admins/reset-password/<int:user_id>', methods=['POST'])
@login_required
def admin_reset_subadmin_password(user_id):
    if not current_user.is_super_admin:
        abort(403)
    user = db.get_or_404(User, user_id)
    new_pw = request.form.get('new_password','').strip()
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin_manage_admins'))
    user.set_password(new_pw)
    db.session.commit()
    flash(f'Password reset for "{user.username}".', 'success')
    return redirect(url_for('admin_manage_admins'))



@app.route('/admin/queries')
@login_required
def admin_queries():
    require_super_admin()
    status   = request.args.get('status', 'all')   # all | unread | resolved
    subject  = request.args.get('subject', 'all')
    page     = request.args.get('page', 1, type=int)

    q = ContactQuery.query
    if status == 'unread':   q = q.filter_by(is_read=False)
    if status == 'resolved': q = q.filter_by(is_resolved=True)
    if status == 'pending':  q = q.filter_by(is_resolved=False)
    if subject != 'all':     q = q.filter_by(subject=subject)

    queries = q.order_by(ContactQuery.submitted_at.desc()).paginate(page=page, per_page=15, error_out=False)
    unread_count = ContactQuery.query.filter_by(is_read=False).count()

    return render_template('admin/queries.html',
                           queries=queries, unread_count=unread_count,
                           status=status, subject_filter=subject)


@app.route('/admin/queries/<int:query_id>')
@login_required
def admin_view_query(query_id):
    require_super_admin()
    query = db.get_or_404(ContactQuery, query_id)
    if not query.is_read:
        query.is_read = True
        db.session.commit()
    return render_template('admin/view_query.html', query=query)


@app.route('/admin/queries/<int:query_id>/resolve', methods=['POST'])
@login_required
def admin_resolve_query(query_id):
    require_super_admin()
    query = db.get_or_404(ContactQuery, query_id)
    query.is_resolved = not query.is_resolved
    note = request.form.get('admin_note', '').strip()
    if note:
        query.admin_note = note
    db.session.commit()
    flash(f'Query marked as {"resolved" if query.is_resolved else "pending"}.', 'success')
    return redirect(url_for('admin_view_query', query_id=query_id))


@app.route('/admin/queries/<int:query_id>/delete', methods=['POST'])
@login_required
def admin_delete_query(query_id):
    require_super_admin()
    query = db.get_or_404(ContactQuery, query_id)
    db.session.delete(query)
    db.session.commit()
    flash('Query deleted.', 'info')
    return redirect(url_for('admin_queries'))


@app.route('/admin/queries/bulk', methods=['POST'])
@login_required
def admin_bulk_queries():
    require_super_admin()
    action = request.form.get('bulk_action')
    ids    = request.form.getlist('selected_ids')
    if not ids:
        flash('No queries selected.', 'warning')
        return redirect(url_for('admin_queries'))
    count = 0
    for qid in ids:
        q = db.session.get(ContactQuery, int(qid))
        if not q: continue
        if action == 'mark_read':    q.is_read = True;      count += 1
        if action == 'resolve':      q.is_resolved = True;  count += 1
        if action == 'delete':       db.session.delete(q);  count += 1
    db.session.commit()
    flash(f'Bulk action applied to {count} queries.', 'success')
    return redirect(url_for('admin_queries'))


@app.route('/admin/comments')
@login_required
def admin_comments():
    require_admin()
    status = request.args.get('status', 'pending')
    page   = request.args.get('page', 1, type=int)

    q = Comment.query
    if status == 'pending':  q = q.filter_by(is_approved=False, is_rejected=False)
    if status == 'approved': q = q.filter_by(is_approved=True,  is_rejected=False)
    if status == 'rejected': q = q.filter_by(is_rejected=True)

    comments = q.order_by(Comment.submitted_at.desc()).paginate(page=page, per_page=20, error_out=False)
    pending_count = Comment.query.filter_by(is_approved=False, is_rejected=False).count()

    return render_template('admin/comments.html',
                           comments=comments, status=status, pending_count=pending_count)


@app.route('/admin/comments/<int:comment_id>/approve', methods=['POST'])
@login_required
def admin_approve_comment(comment_id):
    require_admin()
    comment = db.get_or_404(Comment, comment_id)
    comment.is_approved = True
    comment.is_rejected = False
    db.session.commit()
    flash('Comment approved and visible on the article.', 'success')
    return redirect(request.referrer or url_for('admin_comments'))


@app.route('/admin/comments/<int:comment_id>/reject', methods=['POST'])
@login_required
def admin_reject_comment(comment_id):
    require_admin()
    comment = db.get_or_404(Comment, comment_id)
    comment.is_approved = False
    comment.is_rejected = True
    db.session.commit()
    flash('Comment rejected and hidden.', 'info')
    return redirect(request.referrer or url_for('admin_comments'))


@app.route('/admin/comments/<int:comment_id>/delete', methods=['POST'])
@login_required
def admin_delete_comment(comment_id):
    require_admin()
    comment = db.get_or_404(Comment, comment_id)
    db.session.delete(comment)
    db.session.commit()
    flash('Comment deleted permanently.', 'info')
    return redirect(request.referrer or url_for('admin_comments'))


@app.route('/admin/comments/bulk', methods=['POST'])
@login_required
def admin_bulk_comments():
    require_admin()
    action = request.form.get('bulk_action')
    ids    = request.form.getlist('selected_ids')
    if not ids:
        flash('No comments selected.', 'warning')
        return redirect(url_for('admin_comments'))
    count = 0
    for cid in ids:
        c = db.session.get(Comment, int(cid))
        if not c: continue
        if action == 'approve': c.is_approved=True;  c.is_rejected=False; count+=1
        if action == 'reject':  c.is_rejected=True;  c.is_approved=False; count+=1
        if action == 'delete':  db.session.delete(c); count+=1
    db.session.commit()
    flash(f'Bulk action applied to {count} comments.', 'success')
    return redirect(url_for('admin_comments'))

@app.route('/api/categories')
def api_categories():
    return jsonify(CATEGORIES)

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(error):
    flash('Access denied.', 'danger')
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


# ─────────────────────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        from sqlalchemy import inspect, text
        inspector    = inspect(db.engine)
        user_cols    = [c['name'] for c in inspector.get_columns('user')]
        news_cols    = [c['name'] for c in inspector.get_columns('news')]

        user_migrations = [
            ('is_active',   'BOOLEAN NOT NULL DEFAULT 1'),
            ('profile_pic', 'VARCHAR(500)'),
            ('bio',         'VARCHAR(300)'),
            ('joined_at',   'DATETIME'),
        ]
        for col, defn in user_migrations:
            if col not in user_cols:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE user ADD COLUMN {col} {defn}'))
                    conn.commit()
                print(f'[Migration] user.{col} added.')

        # super admin column
        if 'is_super_admin' not in user_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE user ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT 0'))
                conn.commit()
            print('[Migration] user.is_super_admin added.')

        news_migrations = [
            ('is_admin_post', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('is_approved',   'BOOLEAN NOT NULL DEFAULT 1'),
        ]

        # comment table migration
        try:
            comment_cols = [c['name'] for c in inspector.get_columns('comment')]
            if 'is_rejected' not in comment_cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE comment ADD COLUMN is_rejected BOOLEAN NOT NULL DEFAULT 0'))
                    conn.commit()
                print('[Migration] comment.is_rejected added.')
            if 'parent_id' not in comment_cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE comment ADD COLUMN parent_id INTEGER'))
                    conn.commit()
                print('[Migration] comment.parent_id added.')
        except Exception:
            pass  # table doesn't exist yet

        # contact_query table migration (add missing cols if table exists)
        try:
            cq_cols = [c['name'] for c in inspector.get_columns('contact_query')]
            if 'admin_note' not in cq_cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE contact_query ADD COLUMN admin_note TEXT'))
                    conn.commit()
                print('[Migration] contact_query.admin_note added.')
        except Exception:
            pass  # table doesn't exist yet, db.create_all() will create it
        for col, defn in news_migrations:
            if col not in news_cols:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE news ADD COLUMN {col} {defn}'))
                    conn.commit()
                print(f'[Migration] news.{col} added.')

        try:
            if not User.query.filter_by(is_super_admin=True).first():
                super_admin = User(
                    username='admin', email='admin@newsstream.com',
                    is_admin=True, is_super_admin=True
                )
                super_admin.set_password('admin123')
                db.session.add(super_admin)
                db.session.commit()
                print('[Seed] Super Admin created: admin / admin123')
                print('[Seed] Admin login URL: http://127.0.0.1:5000/admin/login')
        except Exception as e:
            print(f'[Seed] {e}')
            db.session.rollback()

    app.run(debug=True)