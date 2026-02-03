import os
import sys
import shutil
import logging
import argparse
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add paths to sys.path to import project modules
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # generate_report_test
sys.path.append(project_root)

try:
    from utils import sql_config as config
    from server_config import get_user_report_dir, REPORT_DIR
except ImportError as e:
    logger.error(f"Import failed: {e}")
    logger.error(f"sys.path: {sys.path}")
    sys.exit(1)

def get_db_connection():
    encoded_password = quote_plus(config.password)
    db_url = f"mysql+pymysql://{config.username}:{encoded_password}@{config.host}:{config.port}/{config.database}"
    return create_engine(db_url)

def clean_templates(dry_run=True):
    """
    Clean up reports ending with '##模板##' from both DB and File System.
    """
    logger.info(f"Starting cleanup process. Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    
    try:
        engine = get_db_connection()
        conn = engine.connect()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return

    trans = conn.begin()
    
    try:
        # 1. Find target reports
        # Join with report_type to get type_name for file path construction
        sql = text("""
            SELECT r.id, r.report_name, r.user_id, t.type_name 
            FROM report_name r
            JOIN report_type t ON r.type_id = t.id
            WHERE r.report_name LIKE :suffix
        """)
        
        suffix_pattern = '%##模板##'
        targets = conn.execute(sql, {"suffix": suffix_pattern}).fetchall()
        
        logger.info(f"Found {len(targets)} template reports to clean.")
        
        for row in targets:
            rid, rname, uid, tname = row
            
            logger.info(f"Processing Report -> ID: {rid}, Name: {rname}, User: {uid}, Type: {tname}")
            
            # ---------------------------
            # 2. Clean File System
            # ---------------------------
            # Path logic matches import_doc_to_db.py:
            # output_dir = os.path.join(user_report_base, report_type_str, report_name_str)
            
            user_report_root = get_user_report_dir(uid)
            report_dir = os.path.join(user_report_root, tname, rname)
            
            if os.path.exists(report_dir):
                if dry_run:
                    logger.info(f"  [Dry Run] Would delete directory: {report_dir}")
                else:
                    try:
                        shutil.rmtree(report_dir)
                        logger.info(f"  Deleted directory: {report_dir}")
                    except Exception as e:
                        logger.error(f"  Failed to delete directory {report_dir}: {e}")
            else:
                logger.warning(f"  Directory not found (already deleted?): {report_dir}")

            # ---------------------------
            # 3. Clean Database
            # ---------------------------
            if dry_run:
                logger.info(f"  [Dry Run] Would delete DB records for report_id: {rid}")
            else:
                # a. Delete report_chapter_content 
                # (Manual cleanup needed as it has NO Foreign Key constraint in schema)
                sql_del_content = text("""
                    DELETE cc 
                    FROM report_chapter_content cc 
                    JOIN report_catalogue c ON cc.catalogue_id = c.id 
                    WHERE c.report_name_id = :rid
                """)
                res_cc = conn.execute(sql_del_content, {"rid": rid})
                logger.info(f"  Deleted {res_cc.rowcount} rows from report_chapter_content")
                
                # b. Delete report_name 
                # (Cascades to report_catalogue and report_merged_record via FK constraints)
                sql_del_report = text("DELETE FROM report_name WHERE id = :rid")
                res_r = conn.execute(sql_del_report, {"rid": rid})
                logger.info(f"  Deleted report_name record (ID: {rid}).")

        # ---------------------------
        # 4. Clean Orphan Files (FS Scan)
        # ---------------------------
        logger.info("Starting Orphan File Scan...")
        # Structure: REPORT_DIR / user_id / report_type / report_name
        
        if os.path.exists(REPORT_DIR):
            for user_id in os.listdir(REPORT_DIR):
                user_path = os.path.join(REPORT_DIR, user_id)
                if not os.path.isdir(user_path): continue
                
                for type_name in os.listdir(user_path):
                    type_path = os.path.join(user_path, type_name)
                    if not os.path.isdir(type_path): continue
                    
                    for report_name in os.listdir(type_path):
                        if report_name.endswith('##模板##'):
                            report_path = os.path.join(type_path, report_name)
                            if os.path.isdir(report_path):
                                if dry_run:
                                    logger.info(f"  [Dry Run] Found ORPHAN directory: {report_path}")
                                else:
                                    try:
                                        shutil.rmtree(report_path)
                                        logger.info(f"  Deleted ORPHAN directory: {report_path}")
                                    except Exception as e:
                                        logger.error(f"  Failed to delete orphan {report_path}: {e}")

        if dry_run:
            trans.rollback()
            logger.info("Dry run completed. No DB changes committed.")
        else:
            trans.commit()
            logger.info("Cleanup completed successfully. All changes committed.")
            
    except Exception as e:
        trans.rollback()
        logger.error(f"Error occurred during processing: {e}")
        # Re-raise to show traceback if needed, or just exit
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Clean up template reports ending with "##模板##".')
    parser.add_argument('--execute', action='store_true', help='Execute the deletion (default is dry-run)')
    args = parser.parse_args()
    
    # Default is dry_run=True unless --execute is passed
    clean_templates(dry_run=not args.execute)
