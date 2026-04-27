"""
Run this ONCE to set your admin account as Super Admin.
Usage: python fix_super_admin.py
"""
from app import app
from database import db, User

with app.app_context():
    # Find the admin user
    admin = User.query.filter_by(username='admin').first()

    if not admin:
        print("ERROR: No user with username 'admin' found.")
        print("Existing admin accounts:")
        for u in User.query.filter_by(is_admin=True).all():
            print(f"  id={u.id}  username={u.username}  is_super_admin={u.is_super_admin}")
    else:
        print(f"Found: username='{admin.username}'  is_admin={admin.is_admin}  is_super_admin={admin.is_super_admin}")
        admin.is_admin = True
        admin.is_super_admin = True
        db.session.commit()
        print("SUCCESS: admin account is now Super Admin.")
        print("Restart your Flask app and log in again.")

    # Show all admins
    print("\nAll admin accounts:")
    for u in User.query.filter_by(is_admin=True).all():
        print(f"  id={u.id}  username={u.username}  is_super_admin={u.is_super_admin}  is_active={u.is_active}")