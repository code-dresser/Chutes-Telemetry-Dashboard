import sqlite3
import os

DB_PATH = "chutes_telemetry.db"

def initialize_database():
    print(f"Initializing database at: {DB_PATH}")
    
    # Connect to SQLite (this automatically creates the file if it doesn't exist)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create the telemetry table with the exact schema we need
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry (
            timestamp DATETIME,
            name TEXT,
            utilization REAL,
            instances INTEGER,
            action_taken TEXT
        )
    ''')
    print("✓ Table 'telemetry' created successfully.")
    
    # 2. Create an Index on the timestamp column for lightning-fast lookups and deletions
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_timestamp 
        ON telemetry(timestamp)
    ''')
    print("✓ Index 'idx_timestamp' created successfully.")
    
    # 3. Create an Index on the name column to speed up Pandas filtering
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_name 
        ON telemetry(name)
    ''')
    print("✓ Index 'idx_name' created successfully.")
    
    conn.commit()
    conn.close()
    
    print("Database setup complete! You are ready to run the dashboard.")

if __name__ == "__main__":
    initialize_database()