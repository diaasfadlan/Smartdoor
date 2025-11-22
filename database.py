import pymysql
import os

def get_db_connection():
    """Buat koneksi ke MySQL database"""
    connection = pymysql.connect(
        host=os.getenv('MYSQLHOST', 'mysql.railway.internal'),  # ganti dengan PUBLIC HOST
        user=os.getenv('MYSQLUSER', 'root'),
        password=os.getenv('MYSQLPASSWORD', 'ynUANFrkQCctsInFeiAvpNvpMRIztOsZ'),
        database=os.getenv('MYSQLDATABASE', 'db_smartdoor'),
        port=int(os.getenv('MYSQLPORT', 3306)),  # ganti dengan PUBLIC PORT dari Railway
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )
    return connection


def init_db():
    """Inisialisasi database - buat table kalau belum ada"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Buat table users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Buat table logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            status VARCHAR(50),
            image_path VARCHAR(255),
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert default user (username: admin, password: admin)
    cursor.execute("""
        INSERT IGNORE INTO users (username, password) 
        VALUES ('admin', 'diasgantengbanget')
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database initialized!")



