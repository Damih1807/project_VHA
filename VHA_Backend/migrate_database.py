#!/usr/bin/env python3
"""
Migration script để cập nhật database schema
"""

from app import app
from models.models_db import db
from sqlalchemy import text

def migrate_database():
    """Chạy migration để cập nhật database schema"""
    with app.app_context():
        try:
            result = db.session.execute(text("""
                SELECT column_name, data_type, character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name = 'file_documents' AND column_name = 'id'
            """))
            
            column_info = result.fetchone()
            if column_info:
                print(f"Current FileDocument.id: {column_info}")
                
                if column_info[2] and column_info[2] < 36:
                    print("Updating FileDocument.id field to VARCHAR(36)...")
                    db.session.execute(text("""
                        ALTER TABLE file_documents 
                        ALTER COLUMN id TYPE VARCHAR(36)
                    """))
                    db.session.commit()
                    print("FileDocument.id field updated successfully")
                else:
                    print("FileDocument.id field is already correct")
            else:
                print("FileDocument table or id column not found")
                
        except Exception as e:
            print(f"Migration error: {e}")
            db.session.rollback()

if __name__ == "__main__":
    migrate_database() 