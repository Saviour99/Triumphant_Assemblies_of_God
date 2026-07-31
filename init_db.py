import pymysql as MySQLdb  # PyMySQL as a drop-in, matching app/__init__.py
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

# Database connection parameters
HOST = os.getenv('MYSQL_HOST', 'localhost')
USER = os.getenv('MYSQL_USER', 'root')
PASSWORD = os.getenv('MYSQL_PASSWORD', '')
DB = os.getenv('MYSQL_DB', 'Triumphant')


def add_column_if_missing(cursor, table, column, ddl):
    """Idempotent ALTER TABLE ADD COLUMN, compatible with older MySQL/MariaDB
    that don't support 'ADD COLUMN IF NOT EXISTS'. Additive only."""
    cursor.execute(
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE table_schema=%s AND table_name=%s AND column_name=%s""",
        (DB, table, column)
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_database():
    """Initialize database and create tables"""
    try:
        # Connect to MySQL
        conn = MySQLdb.connect(
            host=HOST,
            user=USER,
            passwd=PASSWORD
        )
        cursor = conn.cursor()
        
        # Create database if it doesn't exist
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB}")
        cursor.execute(f"USE {DB}")
        
        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prayer_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                topic VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contact_messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_subscribers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giving (
                id INT AUTO_INCREMENT PRIMARY KEY,
                amount DECIMAL(10, 2) NOT NULL,
                giving_type VARCHAR(100) NOT NULL,
                donor_name VARCHAR(255) NOT NULL,
                donor_email VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_email (donor_email),
                INDEX idx_type (giving_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sermons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                speaker VARCHAR(255) NOT NULL,
                description TEXT,
                youtube_url VARCHAR(500),
                audio_url VARCHAR(500),
                sermon_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_date (sermon_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                event_date DATETIME NOT NULL,
                location VARCHAR(255),
                image_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_date (event_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                category VARCHAR(100),
                author VARCHAR(255),
                image_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_category (category),
                INDEX idx_date (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS testimonies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                testimony TEXT NOT NULL,
                image_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_date (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # ============ CMS: admin / member / management-dashboard tables ============
        # All additive. Never drop or truncate a table here.

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                reset_token VARCHAR(255),
                reset_token_expires_at DATETIME,
                last_login_at DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                phone VARCHAR(50),
                password_hash VARCHAR(255) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                avatar_filename VARCHAR(255),
                reset_token VARCHAR(255),
                reset_token_expires_at DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        add_column_if_missing(cursor, 'members', 'avatar_filename', 'avatar_filename VARCHAR(255) NULL')

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_sermons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                preacher VARCHAR(255) NOT NULL,
                youtube_url VARCHAR(500) NOT NULL,
                message TEXT,
                sermon_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_date (sermon_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_sermons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                preacher VARCHAR(255) NOT NULL,
                audio_path VARCHAR(500) NOT NULL,
                message TEXT,
                sermon_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_date (sermon_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devotions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                quote VARCHAR(500) NULL,
                quote_theme VARCHAR(500) NOT NULL,
                writer_name VARCHAR(255) NOT NULL,
                reflection TEXT NOT NULL,
                prayer_points TEXT NULL,
                declaration TEXT NOT NULL,
                devotion_date DATE NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_devotion_date (devotion_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        add_column_if_missing(cursor, 'devotions', 'prayer_points', 'prayer_points TEXT NULL')
        add_column_if_missing(cursor, 'devotions', 'quote', 'quote VARCHAR(500) NULL')

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ebooks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                author VARCHAR(255) NOT NULL,
                category VARCHAR(20) NOT NULL,
                summary TEXT,
                file_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_category (category)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_stream_settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                is_live BOOLEAN NOT NULL DEFAULT FALSE,
                youtube_url VARCHAR(500),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Extend 'admins' additively: role distinguishes 'admin' vs 'developer'
        # accounts (same dashboard access, different identity), avatar_filename
        # is an optional profile photo.
        add_column_if_missing(cursor, 'admins', 'role',
                               "role VARCHAR(20) NOT NULL DEFAULT 'admin'")
        add_column_if_missing(cursor, 'admins', 'avatar_filename',
                               'avatar_filename VARCHAR(255) NULL')

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_login_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                admin_id INT NOT NULL,
                login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address VARCHAR(64),
                INDEX idx_admin (admin_id),
                CONSTRAINT fk_login_log_admin FOREIGN KEY (admin_id) REFERENCES admins(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Extend the existing 'giving' table additively for member linkage + Paystack tracking.
        add_column_if_missing(cursor, 'giving', 'paystack_reference',
                               'paystack_reference VARCHAR(255) UNIQUE')
        add_column_if_missing(cursor, 'giving', 'status',
                               "status VARCHAR(20) NOT NULL DEFAULT 'pending'")
        add_column_if_missing(cursor, 'giving', 'member_id',
                               'member_id INT NULL')

        # Add the FK separately (can't easily "IF NOT EXISTS" a constraint across
        # MySQL/MariaDB versions) — check information_schema first.
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE table_schema=%s AND table_name='giving' AND constraint_name='fk_giving_member'
        """, (DB,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                ALTER TABLE giving
                ADD CONSTRAINT fk_giving_member FOREIGN KEY (member_id) REFERENCES members(id)
            """)

        # Seed the singleton live-stream settings row (id=1). Never inserted again,
        # never deleted — the app only ever UPDATEs this one row.
        cursor.execute("SELECT COUNT(*) FROM live_stream_settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO live_stream_settings (is_live, youtube_url) VALUES (FALSE, NULL)"
            )

        # Seed a starter reading list for the Worship/Leadership blog pages,
        # once — title/author/summary only, no attached file. Real, publicly
        # known titles are fine to *list* (that's just a bibliography); the
        # admin uploads an actual file later only for books they have the
        # rights to distribute (see CLAUDE.md).
        cursor.execute("SELECT COUNT(*) FROM ebooks")
        if cursor.fetchone()[0] == 0:
            starter_ebooks = [
                ('Worship Matters', 'Bob Kauflin', 'worship',
                 'A foundational guide for anyone who leads music in a church, exploring how '
                 'worship leadership should flow from a right understanding of God and the gospel, '
                 'not just musical skill.'),
                ('The Air I Breathe: Worship as a Way of Life', 'Louie Giglio', 'worship',
                 'Makes the case that worship is not confined to a Sunday song set — it is the '
                 'air a believer breathes in every area of life, from work to rest to relationships.'),
                ('Desiring God: Meditations of a Christian Hedonist', 'John Piper', 'worship',
                 'Argues that pursuing joy in God is not opposed to worshiping Him — it is the '
                 'heart of true worship, reframing holiness as delight rather than duty.'),
                ('Real Worship: Playgrounds, Rituals, and Renewal', 'Warren W. Wiersbe', 'worship',
                 'A classic, searching look at what genuine worship requires beneath the surface '
                 'of routine and religious habit.'),
                ('Unceasing Worship: Biblical Perspectives on Worship and the Arts', 'Harold Best', 'worship',
                 'Explores worship as a continuous outpouring of the whole life, and what that '
                 'means for how the church engages music and the arts.'),
                ('Spiritual Leadership', 'J. Oswald Sanders', 'leadership',
                 'A widely-read classic on the character, calling, and cost of leading others '
                 'in ministry — what sets spiritual leadership apart from leadership in general.'),
                ('The 21 Irrefutable Laws of Leadership', 'John C. Maxwell', 'leadership',
                 'Foundational, practical leadership principles that apply as much to church '
                 'ministry teams as to the workplace.'),
                ('Leaders Eat Last', 'Simon Sinek', 'leadership',
                 'Examines how leaders build genuine trust and loyalty by putting the needs of '
                 'their people first — a servant-leadership case study outside the pulpit.'),
                ('The Serving Leader', 'Ken Jennings & John Stahl-Wert', 'leadership',
                 'A short parable-style book making the case that the most effective leaders '
                 'lead by serving — directly relevant to leading in church, career, or family.'),
                ('Developing the Leader Within You', 'John C. Maxwell', 'leadership',
                 'A practical starting point for anyone discovering and growing their own '
                 'capacity to lead, whatever field or calling they are in.'),
            ]
            cursor.executemany(
                "INSERT INTO ebooks (title, author, category, summary) VALUES (%s, %s, %s, %s)",
                starter_ebooks
            )

        # Seed sample member testimonies, once — clearly-fabricated sample
        # copy (per the site owner's request), not real people's words.
        cursor.execute("SELECT COUNT(*) FROM testimonies")
        if cursor.fetchone()[0] == 0:
            starter_testimonies = [
                ('Ama Mensah',
                 "My life changed completely when I gave my life to Christ at TAG. The love, "
                 "support, and spiritual guidance I've received from this church family has been "
                 "transformational. I went from a life of despair to a life filled with purpose, "
                 "joy, and hope. I'm forever grateful to God and to this wonderful church."),
                ('Kwame Asante',
                 "TAG has been instrumental in my spiritual journey. The powerful sermons, caring "
                 "community, and active ministries have helped me grow in my faith and discover my "
                 "purpose. I've made lifelong friendships and found a true church family."),
                ('Abena Owusu',
                 "Joining TAG was the best decision I ever made. The pastoral care, Bible-based "
                 "teaching, and loving community have strengthened my faith immensely. I've "
                 "witnessed God's faithfulness in my life and seen Him work miracles."),
                ('Efua Boateng',
                 "After years of struggling with anxiety, the prayer team at TAG stood with me "
                 "week after week. Today I walk in a peace I never thought was possible, and I "
                 "know it was God working through this church."),
                ('Kojo Antwi',
                 "I came to TAG after a difficult season of unemployment and financial hardship. "
                 "Through the encouragement of this church and God's faithfulness, I found not "
                 "just a job but a renewed sense of purpose and direction for my life."),
                ('Yaa Asantewaa',
                 "My marriage was falling apart before we joined the couples' fellowship at TAG. "
                 "The godly counsel and the example of other couples in this church restored our "
                 "home. We are stronger and more in love than ever."),
                ('Nana Yeboah',
                 "As a young person, I struggled to find direction until I joined the youth "
                 "ministry at TAG. The mentorship I received here shaped who I am today — I found "
                 "my calling and a family that continues to walk with me."),
            ]
            cursor.executemany(
                "INSERT INTO testimonies (name, testimony) VALUES (%s, %s)",
                starter_testimonies
            )

        # Seed default admin/developer accounts, one time each, keyed on
        # email/username (both are UNIQUE columns) so re-running after the
        # admins table already has rows never collides with an existing
        # account — it just skips seeding that one and leaves it alone.
        def seed_account_if_missing(role, username_env, email_env, password_env,
                                     default_username, default_email, default_password):
            username = os.getenv(username_env, default_username)
            email = os.getenv(email_env, default_email)
            password = os.getenv(password_env, default_password)

            cursor.execute(
                "SELECT COUNT(*) FROM admins WHERE email = %s OR username = %s",
                (email, username)
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO admins (username, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                """, (username, email, generate_password_hash(password), role))
                print(f"✓ Default {role} account created — username: {username}, "
                      f"email: {email}. Log in and change the password immediately.")
            else:
                print(f"• Skipped seeding {role} account — username '{username}' or "
                      f"email '{email}' already in use by an existing account.")

        seed_account_if_missing(
            'admin', 'ADMIN_DEFAULT_USERNAME', 'ADMIN_DEFAULT_EMAIL', 'ADMIN_DEFAULT_PASSWORD',
            'admin', 'admin@triumphantag.com', 'ChangeMe123!'
        )
        seed_account_if_missing(
            'developer', 'DEVELOPER_DEFAULT_USERNAME', 'DEVELOPER_DEFAULT_EMAIL',
            'DEVELOPER_DEFAULT_PASSWORD', 'developer', 'developer@triumphantag.com', 'ChangeDev123!'
        )

        conn.commit()
        cursor.close()
        conn.close()
        
        print("✓ Database initialized successfully!")
        print(f"✓ Database '{DB}' created with all tables")
        
    except MySQLdb.Error as e:
        print(f"✗ Database error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == '__main__':
    init_database()