# pages/Email_Display.py
import streamlit as st
import base64
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime
import pytz

# Configure page settings
st.set_page_config(
    page_title="Email Extractor - Emails",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "logged_in_email" not in st.session_state:
    st.session_state.logged_in_email = None
if "emails_per_page" not in st.session_state:
    st.session_state.emails_per_page = 10

# Custom CSS for better email display
st.markdown("""
    <style>
        .email-header {
            padding: 10px;
            background-color: #f0f2f6;
            border-radius: 5px;
            margin-bottom: 10px;
        }
        .stButton button {
            width: 100%;
        }
        .email-timestamp {
            color: #666;
            font-size: 0.9em;
        }
    </style>
""", unsafe_allow_html=True)

st.title("📧 Your Emails")

def format_timestamp(timestamp):
    """Convert Unix timestamp to readable format."""
    try:
        dt = datetime.fromtimestamp(int(timestamp)/1000.0)
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except:
        return "Unknown date"

def get_google_service():
    """Get authenticated Google service or None."""
    creds = st.session_state.get('credentials')
    
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    elif creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            st.session_state.credentials = creds
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            st.error(f"Error refreshing credentials: {str(e)}")
            return None
    return None

def decode_email_body(payload):
    """Decode the email body and extract inline images."""
    body = ""
    images = {}
    attachments = []

    def process_part(part):
        nonlocal body, images
        
        if 'parts' in part:
            for subpart in part['parts']:
                process_part(subpart)
        else:
            content_type = part.get('mimeType', '')
            if content_type == 'text/html' and 'data' in part.get('body', {}):
                try:
                    decoded = base64.urlsafe_b64decode(part['body']['data']).decode("utf-8")
                    body = decoded if not body else body + decoded
                except Exception:
                    pass
            elif content_type == 'text/plain' and not body and 'data' in part.get('body', {}):
                try:
                    body = base64.urlsafe_b64decode(part['body']['data']).decode("utf-8")
                except Exception:
                    pass
            elif content_type.startswith('image/') and 'filename' in part:
                try:
                    image_data = base64.urlsafe_b64decode(part['body']['data'])
                    content_id = part.get('headers', [{'name': 'Content-ID', 'value': 'unknown'}])[0]['value']
                    images[content_id] = image_data
                except Exception:
                    pass
            elif 'filename' in part and part.get('body', {}).get('attachmentId'):
                attachments.append({
                    'filename': part['filename'],
                    'mimeType': content_type,
                    'attachmentId': part['body']['attachmentId']
                })

    if isinstance(payload, dict):
        process_part(payload)
    
    return body.strip() or "No content available", images, attachments

def fetch_emails(service, max_results=10, page_token=None):
    """Fetch emails from Gmail API."""
    try:
        query_params = {
            'userId': 'me',
            'maxResults': max_results,
            'labelIds': ['INBOX']  # Only fetch inbox emails
        }
        if page_token:
            query_params['pageToken'] = page_token
            
        results = service.users().messages().list(**query_params).execute()
        messages = results.get('messages', [])
        next_page_token = results.get('nextPageToken')
        email_list = []

        with st.spinner('📥 Fetching your emails...'):
            for msg in messages:
                msg_data = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()
                
                headers = msg_data['payload']['headers']
                subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), "No Subject")
                sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), "Unknown Sender")
                date = next((header['value'] for header in headers if header['name'].lower() == 'date'), None)
                
                body, images, attachments = decode_email_body(msg_data['payload'])
                
                # Get labels
                labels = msg_data.get('labelIds', [])
                
                email_list.append({
                    "id": msg['id'],
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "body": body,
                    "images": images,
                    "attachments": attachments,
                    "labels": labels,
                    "timestamp": msg_data['internalDate']
                })

        return email_list, next_page_token
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return [], None

def display_email(email, service):
    """Display a single email with all its components."""
    with st.expander(f"📧 {email['subject']}", expanded=False):
        # Email header
        st.markdown(f"""
            <div class="email-header">
                <strong>From:</strong> {email['from']}<br>
                <strong>Subject:</strong> {email['subject']}<br>
                <span class="email-timestamp">
                    {format_timestamp(email['timestamp'])}
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        # Labels
        if email['labels']:
            st.markdown("**Labels:** " + ", ".join(email['labels']))
        
        # Email body
        st.write("**Content:**")
        st.components.v1.html(email['body'], height=600, scrolling=True)
        
        # Images
        if email['images']:
            st.write("📷 **Inline Images:**")
            cols = st.columns(min(len(email['images']), 3))
            for idx, (content_id, image_data) in enumerate(email['images'].items()):
                with cols[idx % 3]:
                    st.image(image_data, use_column_width=True)
        
        # Attachments
        if email['attachments']:
            st.write("📎 **Attachments:**")
            for attachment in email['attachments']:
                st.write(f"- {attachment['filename']} ({attachment['mimeType']})")

def main():
    service = get_google_service()
    
    # Show logout button if logged in
    if st.session_state.logged_in_email:
        st.success(f"📨 Logged in as: {st.session_state.logged_in_email}")
        col1, col2, col3 = st.columns([2,2,1])
        with col3:
            if st.button("🚪 Log out"):
                st.session_state.clear()
                st.switch_page("Home.py")
    
    # If not authenticated, redirect to home page
    if not service:
        st.warning("⚠️ Please sign in first")
        st.switch_page("Home.py")
        return

    # If service exists but email not set, get user profile
    if not st.session_state.logged_in_email:
        try:
            profile = service.users().getProfile(userId='me').execute()
            st.session_state.logged_in_email = profile['emailAddress']
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Error getting user profile: {str(e)}")
            st.switch_page("Home.py")
            return

    # Email display settings
    col1, col2 = st.columns([3, 1])
    with col2:
        st.session_state.emails_per_page = st.selectbox(
            "Emails per page:",
            options=[5, 10, 25, 50],
            index=1
        )

    # Display emails
    emails, next_page_token = fetch_emails(
        service,
        max_results=st.session_state.emails_per_page,
        page_token=st.session_state.page_token
    )
    
    if emails:
        # Display each email
        for email in emails:
            display_email(email, service)

        # Pagination controls
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Previous Page") and st.session_state.page_token:
                st.session_state.page_token = None
                st.experimental_rerun()
        with col2:
            if next_page_token and st.button("Next Page ➡️"):
                st.session_state.page_token = next_page_token
                st.experimental_rerun()
    else:
        st.info("📭 No emails found in your inbox")

if __name__ == "__main__":
    main()