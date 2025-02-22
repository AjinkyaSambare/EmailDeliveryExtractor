import streamlit as st
import pymssql
import pandas as pd
from typing import Dict, Any

def get_connection():
    """Create and return a database connection with error handling."""
    try:
        return pymssql.connect(
            server=st.secrets["AZURE_SQL_SERVER"],
            user=st.secrets["AZURE_SQL_USERNAME"],
            password=st.secrets["AZURE_SQL_PASSWORD"],
            database=st.secrets["AZURE_SQL_DATABASE"]
        )
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None

def create_table_if_not_exists():
    """Create the delivery_details table if it doesn't exist."""
    try:
        conn = get_connection()
        if conn is None:
            return
        cursor = conn.cursor()
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='delivery_details' AND xtype='U')
            CREATE TABLE delivery_details (
                id INT IDENTITY(1,1) PRIMARY KEY,
                delivery NVARCHAR(10),
                price_num FLOAT,
                description NVARCHAR(255),
                order_id NVARCHAR(50),
                delivery_date DATE,
                store NVARCHAR(255),
                tracking_number NVARCHAR(100),
                carrier NVARCHAR(50),
                created_at DATETIME DEFAULT GETDATE(),
                email_id NVARCHAR(100)
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error creating table: {str(e)}")

def insert_into_db(data: Dict[str, Any], email_id: str = None) -> bool:
    """Insert extracted JSON data into database and return success status."""
    try:
        conn = get_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO delivery_details
            (delivery, price_num, description, order_id, delivery_date, store, tracking_number, carrier, email_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("delivery", "no"),
            data.get("price_num", 0.0),
            data.get("description", ""),
            data.get("order_id", ""),
            data.get("delivery_date", None),
            data.get("store", ""),
            data.get("tracking_number", ""),
            data.get("carrier", ""),
            email_id
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error inserting data: {str(e)}")
        return False

def get_delivery_history() -> pd.DataFrame:
    """Fetch all delivery details from the database with error handling."""
    try:
        conn = get_connection()
        if conn is None:
            return pd.DataFrame()
        cursor = conn.cursor()

        # First check if the table exists
        cursor.execute("""
            IF EXISTS (SELECT * FROM sysobjects WHERE name='delivery_details' AND xtype='U')
            BEGIN
                SELECT 1
            END
            ELSE
            BEGIN
                SELECT 0
            END
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            return pd.DataFrame(columns=[
                'id', 'delivery', 'price_num', 'description', 'order_id',
                'delivery_date', 'store', 'tracking_number', 'carrier', 'created_at'
            ])

        query = """
            SELECT id, delivery, price_num, description, order_id, delivery_date,
                   store, tracking_number, carrier, created_at
            FROM delivery_details
            ORDER BY created_at DESC
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.warning(f"Unable to fetch delivery history: {str(e)}")
        return pd.DataFrame(columns=[
            'id', 'delivery', 'price_num', 'description', 'order_id',
            'delivery_date', 'store', 'tracking_number', 'carrier', 'created_at'
        ])

def display_history_table(df: pd.DataFrame):
    """Display historical delivery details in an interactive table."""
    try:
        st.markdown("### 📋 Delivery History")

        if df is None or df.empty:
            st.info("No previous delivery emails analyzed yet.")
            return

        # Format the DataFrame for display
        display_df = df.copy()

        # Format price as currency
        display_df['price_num'] = display_df['price_num'].apply(lambda x: f"${x:.2f}")

        # Format delivery date
        display_df['delivery_date'] = pd.to_datetime(display_df['delivery_date']).dt.strftime('%B %d, %Y')

        # Format created_at timestamp
        display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')

        # Create delivery status column with emojis
        display_df['status'] = display_df['delivery'].apply(
            lambda x: "✅" if x == "yes" else "❌"
        )

        # Reorder and rename columns for display
        columns_to_display = {
            'created_at': 'Analyzed On',
            'status': 'Status',
            'store': 'Store',
            'description': 'Description',
            'price_num': 'Price',
            'delivery_date': 'Delivery Date',
            'tracking_number': 'Tracking Number',
            'carrier': 'Carrier'
        }

        display_df = display_df[columns_to_display.keys()].rename(columns=columns_to_display)

        # Display the interactive table
        st.dataframe(
            display_df,
            hide_index=True,
            column_config={
                "Status": st.column_config.Column(width="small"),
                "Store": st.column_config.Column(width="medium"),
                "Description": st.column_config.Column(width="large"),
                "Price": st.column_config.Column(width="small"),
                "Analyzed On": st.column_config.Column(width="medium"),
            }
        )

    except Exception as e:
        st.error(f"Error displaying history table: {str(e)}")

def get_processing_statistics():
    """Fetch and calculate processing statistics from the database."""
    try:
        conn = get_connection()
        if conn is None:
            return {
                "total_emails": 0,
                "confirmed_deliveries": 0,
                "total_value": 0.00
            }
        
        cursor = conn.cursor()
        
        # Get total emails processed
        cursor.execute("SELECT COUNT(*) FROM delivery_details")
        total_emails = cursor.fetchone()[0]
        
        # Get confirmed deliveries
        cursor.execute("SELECT COUNT(*) FROM delivery_details WHERE delivery = 'yes'")
        confirmed_deliveries = cursor.fetchone()[0]
        
        # Get total value
        cursor.execute("SELECT SUM(price_num) FROM delivery_details")
        total_value = cursor.fetchone()[0] or 0.00
        
        conn.close()
        
        return {
            "total_emails": total_emails,
            "confirmed_deliveries": confirmed_deliveries,
            "total_value": total_value
        }
    except Exception as e:
        st.warning(f"Unable to fetch statistics: {str(e)}")
        return {
            "total_emails": 0,
            "confirmed_deliveries": 0,
            "total_value": 0.00
        }

def cleanup_old_records(days: int = 30):
    """Delete records older than specified number of days."""
    try:
        conn = get_connection()
        if conn is None:
            return False
        
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM delivery_details 
            WHERE created_at < DATEADD(day, -%d, GETDATE())
        """, (days,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error cleaning up old records: {str(e)}")
        return False