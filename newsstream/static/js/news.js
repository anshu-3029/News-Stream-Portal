// NewsStream - news.js

document.addEventListener('DOMContentLoaded', function () {

  // ── CATEGORY FILTER ──────────────────────────────────────
  const categoryFilter = document.getElementById('categoryFilter');
  if (categoryFilter) {
    // Set current selected from URL
    const params = new URLSearchParams(window.location.search);
    const currentCat = params.get('category') || 'general';
    categoryFilter.value = currentCat;

    categoryFilter.addEventListener('change', function () {
      window.location.href = `/?category=${this.value}`;
    });
  }

  // ── BOOKMARK BUTTONS ─────────────────────────────────────
  document.querySelectorAll('.bookmark-btn').forEach(btn => {
    btn.addEventListener('click', function (e) {
      e.stopPropagation(); // prevent card click
      const newsId = this.dataset.newsId;

      fetch(`/bookmark/${newsId}`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(res => {
        if (res.redirected && res.url.includes('/login')) {
          window.location.href = '/login';
          return;
        }
        // Toggle icon
        const icon = this.querySelector('i');
        if (icon.classList.contains('bi-star-fill')) {
          icon.classList.replace('bi-star-fill', 'bi-star');
          icon.classList.remove('text-warning');
          showToast('Removed from bookmarks', 'info');
        } else {
          icon.classList.replace('bi-star', 'bi-star-fill');
          icon.classList.add('text-warning');
          showToast('Bookmarked!', 'success');
        }
      })
      .catch(() => {
        window.location.href = `/bookmark/${newsId}`;
      });
    });
  });

  // ── TOAST NOTIFICATION ───────────────────────────────────
  function showToast(msg, type = 'success') {
    const colors = {
      success: '#52c47a',
      info: '#4f8ef7',
      warning: '#f5a623',
      error: '#e05252'
    };
    const toast = document.createElement('div');
    toast.style.cssText = `
      position: fixed; bottom: 30px; right: 30px; z-index: 9999;
      background: #111118; color: #f0ede8;
      border: 1px solid rgba(255,255,255,0.08);
      border-left: 3px solid ${colors[type] || colors.success};
      border-radius: 10px; padding: 0.9rem 1.4rem;
      font-family: 'DM Sans', sans-serif; font-size: 0.88rem; font-weight: 500;
      box-shadow: 0 8px 30px rgba(0,0,0,0.5);
      transform: translateY(20px); opacity: 0;
      transition: all 0.3s cubic-bezier(0.4,0,0.2,1);
    `;
    toast.textContent = msg;
    document.body.appendChild(toast);

    requestAnimationFrame(() => {
      toast.style.transform = 'translateY(0)';
      toast.style.opacity = '1';
    });

    setTimeout(() => {
      toast.style.transform = 'translateY(20px)';
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 2500);
  }

  // ── NEWS CARD ANIMATION ON LOAD ──────────────────────────
  const cards = document.querySelectorAll('.news-card');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry, i) => {
        if (entry.isIntersecting) {
          entry.target.style.animationDelay = `${(i % 4) * 60}ms`;
          entry.target.classList.add('card-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    cards.forEach(card => {
      card.style.opacity = '0';
      card.style.transform = 'translateY(16px)';
      card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      observer.observe(card);
    });
  }

  // trigger visible class
  document.querySelectorAll('.card-visible').forEach(card => {
    card.style.opacity = '1';
    card.style.transform = 'translateY(0)';
  });

  // For browsers without IntersectionObserver, just show all
  setTimeout(() => {
    cards.forEach(card => {
      card.style.opacity = '1';
      card.style.transform = 'translateY(0)';
    });
  }, 100);

  // ── ADMIN FEATURE TOGGLE ─────────────────────────────────
  const addFormToggle = document.getElementById('addFormToggle');
  const addNewsForm = document.getElementById('addNewsForm');
  if (addFormToggle && addNewsForm) {
    addFormToggle.addEventListener('click', function () {
      addNewsForm.classList.toggle('d-none');
      this.innerHTML = addNewsForm.classList.contains('d-none')
        ? '<i class="bi bi-plus-lg me-2"></i>Add News'
        : '<i class="bi bi-x-lg me-2"></i>Cancel';
    });
  }
});
