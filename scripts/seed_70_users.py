import sys
import psycopg2
from psycopg2.extras import execute_values
import random
import string

def get_random_string(length):
    return ''.join(random.choices(string.ascii_lowercase, k=length))

def seed_users():
    conn = psycopg2.connect(
        dbname="pdf_editor",
        user="pdf_user",
        password="pdf_password",
        host="db",
        port="5432"
    )
    cursor = conn.cursor()
    
    users = []
    for i in range(1, 71):
        email = f"testuser_{i}_{get_random_string(4)}@example.com"
        # hashed_password for 'Password123'
        hashed_password = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQqiRQYm"
        is_admin = False
        is_verified = True
        is_active = random.choice([True, True, True, False]) # 25% chance inactive
        plan_type = random.choice(['free', 'free', 'pro', 'premium'])
        
        users.append((email, hashed_password, is_admin, is_verified, is_active, plan_type))

    query = """
        INSERT INTO users (email, hashed_password, is_admin, is_verified, is_active, plan_type)
        VALUES %s
    """
    
    execute_values(cursor, query, users)
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"Successfully inserted {len(users)} mock users.")

if __name__ == "__main__":
    seed_users()
