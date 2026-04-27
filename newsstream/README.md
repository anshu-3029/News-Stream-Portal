# NewsStream — Live News Portal

A full-stack Flask news portal with live API news, AI summaries, bookmarks, user auth, and an admin panel.

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

Edit `.env`:
```
SECRET_KEY=your-super-secret-key
NEWS_API_KEY=your_key_from_newsapi.org   # Free at https://newsapi.org
```

### 3. Run the app
```bash
python app.py
```

Visit **http://localhost:5000**

---

## 🔑 Default Admin Login
| Username | Password  |
|----------|-----------|
| admin    | admin123  |

Change this immediately in production!

---

## 📁 Project Structure
```
newsstream/
├── app.py                  # Flask routes & logic
├── config.py               # Configuration
├── database.py             # SQLAlchemy models
├── requirements.txt
├── .env.example
├── static/
│   ├── css/style.css       # Full dark editorial theme
│   └── js/news.js          # Bookmarks, filters, toasts
└── templates/
    ├── base.html           # Navbar + layout
    ├── index.html          # Homepage + carousel
    ├── news-detail.html    # Article detail + AI summary
    ├── login.html
    ├── register.html
    ├── admin.html          # Admin panel
    ├── 404.html
    ├── 500.html
    └── user/
        ├── dashboard.html  # User bookmarks
        ├── about.html
        └── contact.html
```

---

## ✨ Features
- 📰 **Live news** via NewsAPI (6 categories)
- 🎠 **Trending carousel** on homepage
- 🤖 **AI summary** on every article detail page
- ⭐ **Bookmark** articles (AJAX, no page reload)
- 👤 **User auth** — register, login, logout
- 🛡️ **Admin panel** — add/delete/feature articles
- 📄 **Pagination** on news grid
- ⚠️ **404 & 500** error pages
- 📱 **Responsive** mobile-friendly layout

---

## 🗺️ Routes
| Route | Description |
|-------|-------------|
| `/` | Homepage with trending + news grid |
| `/news/<id>` | Article detail with AI summary |
| `/bookmark/<id>` | Toggle bookmark (POST, login required) |
| `/dashboard` | User dashboard with saved articles |
| `/login` | Login page |
| `/register` | Register page |
| `/admin` | Admin panel (admin only) |
| `/admin/add` | Add article (POST, admin only) |
| `/admin/delete/<id>` | Delete article (POST, admin only) |
| `/about` | About page |
| `/contact` | Contact page |
| `/api/categories` | JSON list of categories |
