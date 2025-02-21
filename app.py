import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import requests
import json
import re
import pymssql
import pandas as pd
from datetime import datetime
import pytz
import time
from typing import Dict, Any, List

# Initialize session states
if 'credentials' not in st.session_state:
    st.session_state.credentials = None
if 'auth_in_progress' not in st.session_state:
    st.session_state.auth_in_progress = False
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

class AzureOpenAIChat:
    def __init__(self):
        """Initialize API credentials from Streamlit secrets."""
        self.API_ENDPOINT = st.secrets.get("AZURE_OPENAI_API_ENDPOINT", "")
        self.API_KEY = st.secrets.get("AZURE_OPENAI_API_KEY", "")

    def extract_delivery_details(self, email_body: str, max_tokens: int = 300) -> Dict[str, Any]:
        """Send an email body to Azure OpenAI and extract structured delivery-related details."""
        headers = {
            "Content-Type": "application/json",
            "api-key": self.API_KEY,
        }

        prompt = f"""
        Extract delivery-related details from the following email body and return a JSON output with these keys:
        - delivery: "yes" if delivery is confirmed, otherwise "no".
        - price_num: Extracted price amount, default to 0.00 if not found.
        - description: Short description of the product if available.
        - order_id: Extracted order ID if available.
        - delivery_date: Extracted delivery date in YYYY-MM-DD format if available.
        - store: Store or sender name.
        - tracking_number: Extracted tracking number if available.
        - carrier: Extracted carrier name (FedEx, UPS, USPS, etc.) if available.

        Email Body:
        {email_body}

        Output JSON:
        """

        data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.5,
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        }

        try:
            response = requests.post(self.API_ENDPOINT, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error calling Azure OpenAI API: {str(e)}")
            return None

def is_delivery_related(subject, snippet):
    """
    Check if the email is delivery-related based on more precise keyword matching
    Uses context-aware patterns to reduce false positives
    """
    text = (subject + ' ' + snippet).lower()
    
    # Common false positive words that should be excluded
    exclusion_words = ['certificate', 'training', 'course', 'class', 'workshop', 'webinar']
    
    # If any exclusion word is present, check if it's actually not a delivery context
    for word in exclusion_words:
        if word in text:
            return False
            
    # Check for delivery-specific word combinations
    delivery_patterns = [
        ('order', ['shipped', 'delivered', 'delivery', 'arriving', 'tracking']),
        ('package', ['delivered', 'arrival', 'tracking', 'shipped']),
        ('shipping', ['status', 'update', 'confirmation', 'tracking']),
        ('delivery', ['scheduled', 'attempted', 'successful', 'status']),
        ('tracking', ['number', 'status', 'update', 'information']),
    ]
    
    # Check for courier service names
    courier_services = ['fedex', 'ups', 'usps', 'dhl', 'amazon delivery']
    if any(service in text for service in courier_services):
        return True
    
    # Check for delivery-specific patterns
    for main_word, related_words in delivery_patterns:
        if main_word in text:
            if any(related in text for related in related_words):
                return True
    
    # Additional specific phrases that indicate delivery
    specific_phrases = [
        'out for delivery',
        'will be delivered',
        'has been delivered',
        'delivery notification',
        'shipment notification',
        'delivery status',
        'shipping confirmation',
        'arriving',
        'package arrival'
    ]
    
    return any(phrase in text for phrase in specific_phrases)

# Database functions
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

def get_auth_code_from_url():
    """Extract authorization code from URL if present"""
    try:
        query_params = st.experimental_get_query_params()
        if 'code' in query_params:
            return query_params['code'][0]
    except:
        return None
    return None

def create_gmail_service(credentials):
    """Create and return a Gmail service object."""
    try:
        return build('gmail', 'v1', credentials=credentials)
    except Exception as e:
        st.error(f"Error creating Gmail service: {str(e)}")
        return None

def get_client_config():
    """Return the Google client configuration from secrets."""
    return {
        "web": {
            "client_id": st.secrets["google_client_config"]["client_id"],
            "project_id": st.secrets["google_client_config"]["project_id"],
            "auth_uri": st.secrets["google_client_config"]["auth_uri"],
            "token_uri": st.secrets["google_client_config"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["google_client_config"]["auth_provider_x509_cert_url"],
            "client_secret": st.secrets["google_client_config"]["client_secret"],
            "redirect_uris": st.secrets["google_client_config"]["redirect_uris"]
        }
    }

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

def insert_into_db(data: Dict[str, Any], email_id: str) -> bool:
    """Insert extracted JSON data into database and return success status."""
    try:
        conn = get_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO delivery_details
            (delivery, price_num, description, order_id, delivery_date, store, 
             tracking_number, carrier, email_id)
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

def get_email_messages(service, max_results=100):
    """Fetch and process delivery-related emails."""
    try:
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            st.info("No messages found in the inbox.")
            return []
            
        email_data = []
        chat_client = AzureOpenAIChat()
        
        with st.spinner('Processing delivery-related emails...'):
            progress_bar = st.progress(0)
            processed_count = 0
            
            for message in messages:
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                headers = msg['payload']['headers']
                
                subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
                sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
                date_str = next((header['value'] for header in headers if header['name'].lower() == 'date'), '')
                snippet = msg.get('snippet', 'No preview available')
                
                # Only process delivery-related emails
                if is_delivery_related(subject, snippet):
                    try:
                        date_obj = datetime.strptime(date_str.split(' (')[0].strip(), '%a, %d %b %Y %H:%M:%S %z')
                        formatted_date = date_obj.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
                    except:
                        formatted_date = date_str
                    
                    # Extract full email body
                    email_body = ""
                    if 'parts' in msg['payload']:
                        for part in msg['payload']['parts']:
                            if part['mimeType'] == 'text/plain':
                                email_body = part.get('body', {}).get('data', '')
                    else:
                        email_body = msg['payload'].get('body', {}).get('data', '')
                    
                    # Process through GPT
                    response = chat_client.extract_delivery_details(email_body)
                    if response and "choices" in response:
                        extracted_json = response["choices"][0]["message"]["content"]
                        try:
                            parsed_json = json.loads(extracted_json)
                            # Add email metadata
                            parsed_json['email_id'] = message['id']
                            email_data.append(parsed_json)
                            
                            # Store in database
                            insert_into_db(parsed_json, message['id'])
                        except json.JSONDecodeError:
                            st.warning(f"Failed to parse response for email: {subject}")
                
                processed_count += 1
                progress_bar.progress(processed_count / len(messages))
            
            progress_bar.empty()
        return email_data
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return []

def main():
    st.set_page_config(page_title="Delivery Email Analyzer", page_icon="📦", layout="wide")
    st.title("📦 Delivery Email Analyzer")

    # Create database table if it doesn't exist
    create_table_if_not_exists()

    # Auto-refresh settings
    refresh_interval = st.sidebar.slider("Auto-refresh interval (seconds)", 30, 300, 60)
    
    # Check if it's time to refresh
    if time.time() - st.session_state.last_refresh > refresh_interval:
        st.session_state.last_refresh = time.time()
        st.rerun()

    # Authentication and processing
    if st.session_state.credentials is None:
        st.write("Please login to access your Gmail inbox.")
        if st.button("🔐 Login with Gmail"):
            try:
                flow = Flow.from_client_config(
                    get_client_config(),
                    scopes=['https://www.googleapis.com/auth/gmail.readonly'],
                    redirect_uri=st.secrets["google_client_config"]["redirect_uris"][0]
                )
                auth_url, _ = flow.authorization_url(prompt='consent')
                st.session_state.auth_in_progress = True
                st.markdown(f"[Click here to authorize]({auth_url})")
            except Exception as e:
                st.error(f"Error initiating authentication: {str(e)}")
    else:
        # Logout button
        if st.sidebar.button("🚪 Logout"):
            st.session_state.credentials = None
            st.rerun()
        
        # Process emails
        service = create_gmail_service(st.session_state.credentials)
        if service:
            processed_emails = get_email_messages(service)
            
            # Display statistics and history
            st.markdown("### 📊 Recent Processing Results")
            if processed_emails:
                st.success(f"Processed {len(processed_emails)} delivery-related emails")
                
                # Display detailed results
                for email in processed_emails:
                    with st.expander(f"📧 {email.get('description', 'Delivery Details')}"):
                        display_delivery_details(email)
            else:
                st.info("No new delivery-related emails found")
            
            # Display historical data
            display_history_table(get_delivery_history())

if __name__ == "__main__":
    main()