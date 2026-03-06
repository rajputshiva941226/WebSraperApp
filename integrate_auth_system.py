"""
Script to integrate authentication and credit system into app.py
"""

def integrate_auth():
    """Add authentication imports and configurations to app.py"""
    
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already integrated
    if 'from models import db' in content:
        print("⚠️  Authentication system already integrated!")
        return False
    
    # Find the imports section
    import_addition = """from models import db, init_db
from auth_routes import auth_bp
from credit_routes import credit_bp
from master_db_routes import master_db_bp
from flask_login import LoginManager
"""
    
    # Add after other imports
    content = content.replace(
        "from collections import defaultdict",
        f"from collections import defaultdict\n{import_addition}"
    )
    
    # Add database configuration after app creation
    db_config = """
# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///journal_scraper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Initialize database
init_db(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(credit_bp)
app.register_blueprint(master_db_bp)
"""
    
    content = content.replace(
        "app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB",
        f"app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB\n{db_config}"
    )
    
    # Write back
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Authentication system integrated into app.py!")
    return True

def add_login_link_to_navbar():
    """Update landing page navbar with login link"""
    
    files_to_update = [
        'templates/landing.html',
        'templates/scraper.html',
        'templates/jobs.html',
        'templates/dashboard.html'
    ]
    
    for filename in files_to_update:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Add login link to navbar if not present
            if '/login' not in content and '<div class="nav-links">' in content:
                content = content.replace(
                    '<div class="nav-links">',
                    '''<div class="nav-links">
                {% if session.get('user_id') %}
                    <a href="/profile">👤 {{ session.get('username') }}</a>
                    <a href="/logout">Logout</a>
                {% else %}
                    <a href="/login">Login</a>
                    <a href="/register">Register</a>
                {% endif %}'''
                )
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"✅ Updated navbar in {filename}")
        except FileNotFoundError:
            print(f"⚠️  File not found: {filename}")
        except Exception as e:
            print(f"❌ Error updating {filename}: {e}")

if __name__ == "__main__":
    print("=" * 70)
    print("INTEGRATING AUTHENTICATION & CREDIT SYSTEM")
    print("=" * 70)
    
    if integrate_auth():
        print("\n✅ Integration successful!")
        print("\nNext steps:")
        print("1. Run: python init_database.py")
        print("2. Restart Flask server")
        print("3. Navigate to http://localhost:5000/login")
    else:
        print("\n⚠️  Integration skipped or already done")
    
    print("\n" + "=" * 70)
