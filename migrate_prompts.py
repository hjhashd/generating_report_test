import os
import pymysql
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/root/zzp/langextract-main/generate_report_test/.env')

print("Environment loaded.", flush=True)

# Database Configurations
SOURCE_DB_CONFIG = {
    'host': os.getenv('AGENT_DB_HOST'),
    'port': int(os.getenv('AGENT_DB_PORT') or 3306),
    'user': os.getenv('AGENT_DB_USER'),
    'password': os.getenv('AGENT_DB_PASSWORD'),
    'db': os.getenv('AGENT_DB_NAME'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

TARGET_DB_CONFIG = {
    'host': os.getenv('REPORT_DB_HOST'),
    'port': int(os.getenv('REPORT_DB_PORT') or 3306),
    'user': os.getenv('REPORT_DB_USER'),
    'password': os.getenv('REPORT_DB_PASSWORD'),
    'db': os.getenv('REPORT_DB_NAME'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

print(f"Source Config: Host={SOURCE_DB_CONFIG['host']}, DB={SOURCE_DB_CONFIG['db']}", flush=True)
print(f"Target Config: Host={TARGET_DB_CONFIG['host']}, DB={TARGET_DB_CONFIG['db']}", flush=True)

def migrate():
    print("Connecting to databases...", flush=True)
    try:
        source_conn = pymysql.connect(**SOURCE_DB_CONFIG)
        print(f"Connected to Source: {SOURCE_DB_CONFIG['host']}")
        
        target_conn = pymysql.connect(**TARGET_DB_CONFIG)
        print(f"Connected to Target: {TARGET_DB_CONFIG['host']}")
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    try:
        with source_conn.cursor() as s_cursor, target_conn.cursor() as t_cursor:
            
            # --- Step 1: Migrate Public Prompts ---
            print("\n--- Step 1: Migrating Public Prompts ---")
            s_cursor.execute("SELECT title, content, description, views_count, created_at, updated_at FROM public_prompts")
            public_prompts = s_cursor.fetchall()
            
            migrated_public = 0
            if public_prompts:
                sql = """
                    INSERT INTO ai_prompts 
                    (user_id, user_name, title, content, description, status, view_count, create_time, update_time, uuid, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """
                values = []
                for p in public_prompts:
                    values.append((
                        3, 'admin', p['title'], p['content'], p['description'], 
                        2, p['views_count'] or 0, p['created_at'], p['updated_at'], str(uuid.uuid4())
                    ))
                
                t_cursor.executemany(sql, values)
                migrated_public = len(values)
                print(f"Successfully migrated {migrated_public} public prompts.")
            else:
                print("No public prompts found.")

            # --- Step 2: Migrate User Prompts ---
            print("\n--- Step 2: Migrating User Prompts ---")
            s_cursor.execute("SELECT title, content, description, created_at, updated_at FROM user_prompts")
            user_prompts = s_cursor.fetchall()
            
            migrated_private = 0
            if user_prompts:
                sql = """
                    INSERT INTO ai_prompts 
                    (user_id, user_name, title, content, description, status, view_count, create_time, update_time, uuid, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                """
                values = []
                for p in user_prompts:
                    values.append((
                        3, 'admin', p['title'], p['content'], p['description'], 
                        1, 0, p['created_at'], p['updated_at'], str(uuid.uuid4())
                    ))
                
                t_cursor.executemany(sql, values)
                migrated_private = len(values)
                print(f"Successfully migrated {migrated_private} user prompts.")
            else:
                print("No user prompts found.")

            # --- Step 3: Archive Folder ---
            print("\n--- Step 3: Creating Archive Folder ---")
            
            # Check if folder already exists to avoid duplicate
            t_cursor.execute("SELECT id FROM ai_prompt_directories WHERE dir_name = '📅 历史归档数据' AND owner_id = 3")
            existing_folder = t_cursor.fetchone()
            
            if existing_folder:
                archive_folder_id = existing_folder['id']
                print(f"Archive folder already exists with ID: {archive_folder_id}")
            else:
                # Create folder
                t_cursor.execute("""
                    INSERT INTO ai_prompt_directories 
                    (dir_name, parent_id, owner_id, is_public, sort_order) 
                    VALUES ('📅 历史归档数据', 0, 3, 0, 999)
                """)
                archive_folder_id = t_cursor.lastrowid
                print(f"Created archive folder with ID: {archive_folder_id}")
            
            # Link prompts
            # We link prompts that are NOT already linked to this folder
            # But the table ai_prompt_directory_rel has PK (directory_id, prompt_id), so duplicates will fail if we just insert.
            # We use INSERT IGNORE to be safe.
            
            link_sql = """
                INSERT IGNORE INTO ai_prompt_directory_rel (directory_id, prompt_id)
                SELECT %s, id 
                FROM ai_prompts 
                WHERE user_id = 3 AND department_id IS NULL
            """
            rows = t_cursor.execute(link_sql, (archive_folder_id,))
            print(f"Linked {rows} prompts to the archive folder.")

            target_conn.commit()
            print("\nMigration completed successfully!")

    except Exception as e:
        target_conn.rollback()
        print(f"\nMigration failed: {e}")
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    migrate()
