import json
import psycopg2
import os

def lambda_handler(event, context):
    """Lambda function to create user 60 in RDS PostgreSQL database"""

    # Database connection parameters
    host = "circles-db.cqdweqam0x1u.us-east-1.rds.amazonaws.com"
    port = 5432
    database = "circles"
    username = "circles"
    password = "Circles2025SecureDB123456789"

    try:
        # Connect to the database
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password,
            sslmode='require'
        )

        # Create a cursor
        cur = conn.cursor()

        # Check if user 60 exists
        cur.execute("SELECT id, phone FROM users WHERE id = 60")
        user = cur.fetchone()

        if user:
            result = f"✅ User 60 already exists: {user}"
        else:
            # Create user 60
            cur.execute("""
                INSERT INTO users (id, phone, is_verified, created_at, updated_at)
                VALUES (60, '+2222222222', true, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """)

            # Commit the transaction
            conn.commit()

            # Verify creation
            cur.execute("SELECT id, phone FROM users WHERE id = 60")
            user = cur.fetchone()

            if user:
                result = f"✅ User 60 created successfully: {user}"
            else:
                result = "❌ Failed to create user 60"

        # Close the cursor and connection
        cur.close()
        conn.close()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': result,
                'success': True
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f"❌ Error: {str(e)}",
                'success': False
            })
        }