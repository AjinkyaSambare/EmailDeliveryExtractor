import streamlit as st
import os
import pickle
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
from urllib.parse import parse_qs, urlparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure OAuth settings
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Google API Scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

st.set_page_config(
    page_title="Email Extractor",
    page_icon="📧",
    layout="wide"
)

st.title("📧 Email - Extractor")

# Initialize session state
def init_session_state():
    if "logged_in_email" not in st.session_state:
        st.session_state.logged_in_email = None
    if "page_token" not in st.session_state:
        st.session_state.page_token = None
    if "oauth_state" not in st.session_state:
        st.session_state.oauth_state = None
    if "authentication_attempted" not in st.session_state:
        st.session_state.authentication_attempted = False

init_session_state()

def clear_auth_state():
    """Clear all authentication related state and files."""
    try:
        if os.path.exists("token.pickle"):
            os.remove("token.pickle")
    except Exception as e:
        logger.error(f"Error removing token file: {e}")
    
    st.session_state.logged_in_email = None
    st.session_state.page_token = None
    st.session_state.oauth_state = None
    st.session_state.authentication_attempted = False
    
    # Clear URL parameters
    st.query_params.clear()

def create_oauth_flow():
    """Create and configure OAuth flow."""
    try:
        client_config = st.secrets["google_client_config"]
        redirect_uri = client_config["redirect_uris"][0]
        
        flow = Flow.from_client_config(
            {"web": client_config},
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get new refresh token
        )
        
        st.session_state.oauth_state = state
        return flow, auth_url
    except Exception as e:
        logger.error(f"Error creating OAuth flow: {e}")
        st.error("Failed to initialize authentication. Please try again.")
        return None, None

def handle_oauth_callback(flow):
    """Handle OAuth callback and token exchange."""
    try:
        code = st.query_params.get("code")
        state = st.query_params.get("state")
        
        if code and state:
            flow.fetch_token(code=code)
            creds = flow.credentials
            
            # Save the credentials
            with open("token.pickle", "wb") as token:
                pickle.dump(creds, token)
            
            st.query_params.clear()
            return creds
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        clear_auth_state()
        st.error("Authentication failed. Please try again.")
    return None

def decode_email_body(payload):
    """Decode the email body and extract inline images."""
    body = ""
    images = {}

    try:
        if 'parts' in payload:
            for part in payload['parts']:
                if 'mimeType' not in part:
                    continue
                    
                content_type = part['mimeType']
                
                if content_type == 'text/html' and 'data' in part.get('body', {}):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode("utf-8")
                elif content_type.startswith('image/'):
                    if 'filename' in part and 'data' in part.get('body', {}):
                        try:
                            image_data = base64.urlsafe_b64decode(part['body']['data'])
                            content_id = next((header['value'].strip('<>') 
                                            for header in part.get('headers', []) 
                                            if header['name'].lower() == 'content-id'), 
                                           part['filename'])
                            images[content_id] = image_data
                        except Exception as e:
                            logger.warning(f"Failed to decode image: {e}")

        else:
            if 'body' in payload and 'data' in payload['body']:
                body = base64.urlsafe_b64decode(payload['body']['data']).decode("utf-8")
    except Exception as e:
        logger.error(f"Error decoding email body: {e}")
        body = "Error decoding message content."

    return body.strip(), images

def fetch_emails(service, max_results=10, page_token=None):
    """Fetch emails from Gmail API."""
    try:
        results = service.users().messages().list(
            userId='me', 
            maxResults=max_results, 
            pageToken=page_token
        ).execute()
        
        messages = results.get('messages', [])
        next_page_token = results.get('nextPageToken')
        email_list = []

        for msg in messages:
            try:
                msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
                headers = msg_data['payload']['headers']
                
                subject = next((header['value'] for header in headers 
                              if header['name'].lower() == 'subject'), "No Subject")
                sender = next((header['value'] for header in headers 
                             if header['name'].lower() == 'from'), "Unknown Sender")
                date = next((header['value'] for header in headers 
                           if header['name'].lower() == 'date'), "No Date")
                
                body, images = decode_email_body(msg_data['payload'])
                
                email_list.append({
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "body": body,
                    "images": images
                })
            except Exception as e:
                logger.warning(f"Failed to fetch email details: {e}")
                continue

        return email_list, next_page_token
    except Exception as e:
        logger.error(f"Failed to fetch emails: {e}")
        return [], None

def authenticate_user():
    """Main authentication function."""
    if not st.session_state.authentication_attempted:
        return None

    creds = None

    # Try to load existing credentials
    if os.path.exists("token.pickle"):
        try:
            with open("token.pickle", "rb") as token:
                creds = pickle.load(token)
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            clear_auth_state()
            return None

    # Handle credential refresh or new authentication
    try:
        if creds and creds.valid:
            return build('gmail', 'v1', credentials=creds)
        
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open("token.pickle", "wb") as token:
                    pickle.dump(creds, token)
                return build('gmail', 'v1', credentials=creds)
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                clear_auth_state()
                st.error("Session expired. Please sign in again.")
                return None
        
        # Start new authentication flow
        flow, auth_url = create_oauth_flow()
        if not flow or not auth_url:
            return None
            
        # Check for OAuth callback
        if "code" in st.query_params:
            creds = handle_oauth_callback(flow)
            if creds:
                return build('gmail', 'v1', credentials=creds)
        else:
            # Show sign-in button
            st.markdown(f'''
                <a href="{auth_url}" target="_self">
                    <button style="background-color: #4CAF50; color: white; padding: 12px 20px; 
                    border: none; border-radius: 4px; cursor: pointer;">
                        Sign in with Google
                    </button>
                </a>
            ''', unsafe_allow_html=True)
            
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        clear_auth_state()
        st.error("An error occurred during authentication. Please try again.")
    
    return None

# Initial authentication button
if not st.session_state.authentication_attempted:
    st.write("Welcome to Email Extractor! Click below to sign in with your Google account.")
    if st.button("Sign in with Google", type="primary"):
        st.session_state.authentication_attempted = True
        st.rerun()

# Main authentication flow
if st.session_state.authentication_attempted:
    service = authenticate_user()
    
    if service and not st.session_state.logged_in_email:
        try:
            user_profile = service.users().getProfile(userId='me').execute()
            st.session_state.logged_in_email = user_profile['emailAddress']
            st.rerun()
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            clear_auth_state()
            st.error("Failed to get user profile. Please try signing in again.")

    # Display user interface when logged in
    if st.session_state.logged_in_email:
        st.success(f"Logged in as: {st.session_state.logged_in_email}")
        
        col1, col2 = st.columns([1, 10])
        with col1:
            if st.button("🚪 Log out"):
                clear_auth_state()
                st.rerun()

        # Display Emails
        service = authenticate_user()
        if service:
            try:
                emails, next_page_token = fetch_emails(
                    service, 
                    max_results=10, 
                    page_token=st.session_state.page_token
                )

                if not emails:
                    st.info("No emails found in this page.")
                else:
                    for email in emails:
                        with st.expander(
                            f"📧 {email['subject']} - From: {email['from']} - Date: {email['date']}"
                        ):
                            st.write(f"**From:** {email['from']}")
                            st.write(f"**Date:** {email['date']}")
                            st.write(f"**Subject:** {email['subject']}")
                            st.write("**Body:**")
                            st.components.v1.html(email['body'], height=600, scrolling=True)

                            if email['images']:
                                st.write("📷 **Inline Images:**")
                                for content_id, image_data in email['images'].items():
                                    try:
                                        st.image(
                                            image_data, 
                                            caption=f"Embedded Image: {content_id}", 
                                            use_column_width=True
                                        )
                                    except Exception as e:
                                        st.warning(f"Failed to display image: {str(e)}")

                # Pagination buttons
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⬅️ Previous Page") and st.session_state.page_token is not None:
                        st.session_state.page_token = None
                        st.rerun()
                with col2:
                    if next_page_token:
                        if st.button("➡️ Next Page"):
                            st.session_state.page_token = next_page_token
                            st.rerun()

            except Exception as e:
                logger.error(f"Error fetching emails: {e}")
                st.error("Failed to fetch emails. Please try logging in again.")
                clear_auth_state()
