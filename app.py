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
if 'auth_code' not in st.session_state:
    st.session_state.auth_code = None
if 'processed_emails' not in st.session_state:
    st.session_state.processed_emails = []
if 'total_emails' not in st.session_state:
    st.session_state.total_emails = 0
if 'current_progress' not in st.session_state:
    st.session_state.current_progress = 0

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
    """Fetch and process delivery-related emails with detailed progress tracking."""
    try:
        # Create status containers
        fetch_status = st.empty()
        fetch_progress = st.progress(0)
        process_status = st.empty()
        process_progress = st.progress(0)
        
        fetch_status.text("📥 Fetching emails from Gmail...")
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            fetch_status.info("No messages found in the inbox.")
            return []
            
        email_data = []
        chat_client = AzureOpenAIChat()
        total_messages = len(messages)
        
        fetch_status.text(f"🔍 Found {total_messages} emails to analyze")
        processed_count = 0
        delivery_count = 0
            
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

    # Auto-refresh settings in sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        refresh_interval = st.slider("Auto-refresh interval (seconds)", 30, 300, 60)
        
        if st.session_state.credentials:
            if st.button("🚪 Logout", key="logout"):
                for key in st.session_state.keys():
                    del st.session_state[key]
                st.rerun()

    # Check for authorization code in URL
    auth_code = get_auth_code_from_url()
    if auth_code and not st.session_state.credentials:
        with st.spinner("🔐 Completing authentication..."):
            try:
                flow = Flow.from_client_config(
                    get_client_config(),
                    scopes=['https://www.googleapis.com/auth/gmail.readonly'],
                    redirect_uri=st.secrets["google_client_config"]["redirect_uris"][0]
                )
                flow.fetch_token(code=auth_code)
                st.session_state.credentials = flow.credentials
                st.session_state.auth_in_progress = False
                st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
                st.session_state.auth_in_progress = False

    # Main content area
    if not st.session_state.credentials:
        st.markdown("""
        ### 🔐 Gmail Authentication Required
        Please login to access your Gmail inbox and analyze delivery emails.
        """)
        
        auth_col1, auth_col2 = st.columns([1, 2])
        with auth_col1:
            if st.button("🔑 Login with Gmail", key="login", use_container_width=True):
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
                    st.session_state.auth_in_progress = False
    else:
        # Process emails
        service = create_gmail_service(st.session_state.credentials)
        if service:
            # Progress indicators
            progress_container = st.empty()
            status_container = st.empty()
            results_container = st.empty()
            
            with progress_container.container():
                st.markdown("### 📥 Fetching Emails")
                fetch_progress = st.progress(0)
                process_progress = st.progress(0)
            
            with status_container:
                status_text = st.empty()
                
            # Process emails with progress updates
            status_text.text("📧 Fetching emails from Gmail...")
            processed_emails = get_email_messages(service)
            
            # Update progress and display results
            if processed_emails:
                with results_container:
                    st.success(f"✅ Successfully processed {len(processed_emails)} delivery-related emails")
                    
                    # Statistics
                    st.markdown("### 📊 Processing Statistics")
                    stat_col1, stat_col2, stat_col3 = st.columns(3)
                    
                    with stat_col1:
                        st.metric("Total Emails Processed", len(processed_emails))
                    with stat_col2:
                        confirmed_deliveries = sum(1 for email in processed_emails if email.get('delivery') == 'yes')
                        st.metric("Confirmed Deliveries", confirmed_deliveries)
                    with stat_col3:
                        total_value = sum(float(email.get('price_num', 0)) for email in processed_emails)
                        st.metric("Total Value", f"${total_value:.2f}")
                    
                    # Display detailed results
                    st.markdown("### 📦 Recent Deliveries")
                    for email in processed_emails:
                        with st.expander(f"📧 {email.get('description', 'Delivery Details')}"):
                            display_delivery_details(email)
            else:
                with results_container:
                    st.info("No new delivery-related emails found")
            
            # Clean up progress indicators
            progress_container.empty()
            status_container.empty()
            
            # Display historical data
            st.markdown("---")
            display_history_table(get_delivery_history())
            
    # Check if it's time to refresh
    if time.time() - st.session_state.last_refresh > refresh_interval:
        st.session_state.last_refresh = time.time()
        time.sleep(2)  # Small delay to prevent too frequent refreshes
        st.rerun()

if __name__ == "__main__":
    main()