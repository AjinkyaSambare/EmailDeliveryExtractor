import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime
import pytz
import time
from urllib.parse import urlparse, parse_qs

# Initialize session states
if 'credentials' not in st.session_state:
    st.session_state.credentials = None
if 'auth_in_progress' not in st.session_state:
    st.session_state.auth_in_progress = False
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

# List of delivery-related keywords to filter emails
DELIVERY_KEYWORDS = [
    'delivered', 'delivery', 'shipping', 'shipment', 'tracking', 'package',
    'courier', 'fedex', 'ups', 'usps', 'dhl', 'amazon delivery', 'order shipped',
    'out for delivery', 'arrival', 'dispatched'
]

def get_client_config():
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

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

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
    try:
        return build('gmail', 'v1', credentials=credentials)
    except Exception as e:
        st.error(f"Error creating Gmail service: {str(e)}")
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

def get_email_messages(service, max_results=100):
    try:
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            st.info("No messages found in the inbox.")
            return []
            
        email_data = []
        with st.spinner('Loading delivery-related emails...'):
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
                        
                    email_data.append({
                        'subject': subject,
                        'sender': sender,
                        'date': formatted_date,
                        'snippet': snippet
                    })
        return email_data
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return []

def main():
    st.set_page_config(page_title="Delivery Email Tracker", page_icon="📦", layout="wide")
    st.title("📦 Delivery Email Tracker")

    # Auto-refresh settings
    refresh_interval = st.sidebar.slider("Auto-refresh interval (seconds)", 30, 300, 60)
    
    # Check if it's time to refresh
    if time.time() - st.session_state.last_refresh > refresh_interval:
        st.session_state.last_refresh = time.time()
        st.rerun()

    # Check for authorization code in URL
    auth_code = get_auth_code_from_url()
    
    # Debug info
    st.sidebar.write("Debug Info:")
    st.sidebar.write(f"Auth Code Present: {bool(auth_code)}")
    st.sidebar.write(f"Auth in Progress: {st.session_state.auth_in_progress}")
    st.sidebar.write(f"Has Credentials: {bool(st.session_state.credentials)}")
    st.sidebar.write(f"Last Refresh: {datetime.fromtimestamp(st.session_state.last_refresh).strftime('%H:%M:%S')}")
    
    # Handle authentication and authorization
    if st.session_state.credentials is None:
        if auth_code and not st.session_state.auth_in_progress:
            try:
                st.session_state.auth_in_progress = True
                flow = Flow.from_client_config(
                    get_client_config(),
                    scopes=SCOPES,
                    redirect_uri=st.secrets["google_client_config"]["redirect_uris"][0]
                )
                flow.fetch_token(code=auth_code)
                st.session_state.credentials = flow.credentials
                st.session_state.auth_in_progress = False
                st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
                st.session_state.auth_in_progress = False
        
        if not st.session_state.auth_in_progress:
            st.write("Please login to access your Gmail inbox.")
            if st.button("🔐 Login with Gmail"):
                try:
                    flow = Flow.from_client_config(
                        get_client_config(),
                        scopes=SCOPES,
                        redirect_uri=st.secrets["google_client_config"]["redirect_uris"][0]
                    )
                    auth_url, _ = flow.authorization_url(prompt='consent')
                    st.session_state.auth_in_progress = True
                    st.markdown(f"[Click here to authorize]({auth_url})")
                except Exception as e:
                    st.error(f"Error initiating authentication: {str(e)}")
                    st.session_state.auth_in_progress = False
    else:
        # Logout button
        if st.sidebar.button("🚪 Logout"):
            st.session_state.credentials = None
            st.session_state.auth_in_progress = False
            st.rerun()
        
        # Display emails
        service = create_gmail_service(st.session_state.credentials)
        if service:
            emails = get_email_messages(service)
            if emails:
                st.subheader("Your Delivery-Related Emails")
                
                # Search and filter options
                col1, col2 = st.columns([3, 1])
                with col1:
                    search_term = st.text_input("Search delivery emails", "").lower()
                with col2:
                    sort_by = st.selectbox("Sort by", ["Date", "Sender", "Subject"])
                
                # Filter and sort emails
                filtered_emails = [
                    email for email in emails 
                    if not search_term or 
                    search_term in email['subject'].lower() or 
                    search_term in email['sender'].lower() or 
                    search_term in email['snippet'].lower()
                ]
                
                if sort_by == "Date":
                    filtered_emails.sort(key=lambda x: x['date'], reverse=True)
                elif sort_by == "Sender":
                    filtered_emails.sort(key=lambda x: x['sender'].lower())
                else:
                    filtered_emails.sort(key=lambda x: x['subject'].lower())
                
                # Display emails
                for email in filtered_emails:
                    with st.expander(f"{email['subject']} - {email['sender']}"):
                        st.write(f"**From:** {email['sender']}")
                        st.write(f"**Date:** {email['date']}")
                        st.write(f"**Preview:**")
                        st.write(email['snippet'])
                        st.markdown("---")
            else:
                st.info("No delivery-related emails found in your recent messages.")

if __name__ == "__main__":
    main()