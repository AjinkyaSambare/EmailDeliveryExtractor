import streamlit as st
import os
import pickle
import base64
import json
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Configure page settings
st.set_page_config(page_title="Email Extractor", page_icon="📧", layout="wide")

# Google API Scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

st.title("📧 Email Extractor")

# Initialize session state variables
if "oauth_state" not in st.session_state:
    st.session_state.oauth_state = None
if "logged_in_email" not in st.session_state:
    st.session_state.logged_in_email = None
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "credentials" not in st.session_state:
    st.session_state.credentials = None

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

def setup_google_oauth():
    """Setup Google OAuth flow."""
    if "google_client_config" not in st.secrets:
        st.error("Google client configuration is missing. Please configure the secrets.")
        return None

    config = st.secrets["google_client_config"]
    client_config = {
        "web": {
            "client_id": config["client_id"],
            "project_id": config["project_id"],
            "auth_uri": config["auth_uri"],
            "token_uri": config["token_uri"],
            "auth_provider_x509_cert_url": config["auth_provider_x509_cert_url"],
            "client_secret": config["client_secret"],
            "redirect_uris": config["redirect_uris"]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=config["redirect_uris"][0]
    )
    
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    st.session_state.oauth_state = state
    return auth_url

def decode_email_body(payload):
    """Decode the email body and extract inline images."""
    body = ""
    images = {}

    if 'parts' in payload:
        for part in payload['parts']:
            try:
                content_type = part['mimeType']
                if content_type == 'text/html':
                    body = base64.urlsafe_b64decode(part['body']['data']).decode("utf-8")
                elif content_type.startswith('image/') and 'filename' in part:
                    image_data = base64.urlsafe_b64decode(part['body']['data'])
                    content_id = part.get('headers', [{'value': 'unknown'}])[0]['value'].strip('<>')
                    images[content_id] = image_data
            except Exception as e:
                continue
    else:
        try:
            body = base64.urlsafe_b64decode(payload['body']['data']).decode("utf-8")
        except Exception:
            body = "Could not decode message content."

    return body.strip(), images

def fetch_emails(service, max_results=10, page_token=None):
    """Fetch emails from Gmail API."""
    try:
        query_params = {
            'userId': 'me',
            'maxResults': max_results
        }
        if page_token:
            query_params['pageToken'] = page_token
            
        results = service.users().messages().list(**query_params).execute()
        messages = results.get('messages', [])
        next_page_token = results.get('nextPageToken')
        email_list = []

        with st.spinner('Fetching emails...'):
            for msg in messages:
                msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
                headers = msg_data['payload']['headers']
                subject = next((header['value'] for header in headers if header['name'] == 'Subject'), "No Subject")
                sender = next((header['value'] for header in headers if header['name'] == 'From'), "Unknown Sender")

                body, images = decode_email_body(msg_data['payload'])
                email_list.append({
                    "subject": subject,
                    "from": sender,
                    "body": body,
                    "images": images
                })

        return email_list, next_page_token
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return [], None

# Main app logic
def main():
    service = get_google_service()
    
    # Show logout button if logged in
    if st.session_state.logged_in_email:
        st.success(f"Logged in as: {st.session_state.logged_in_email}")
        if st.button("Log out"):
            st.session_state.clear()
            st.experimental_rerun()
    
    # If not logged in, show login button
    if not service:
        auth_url = setup_google_oauth()
        if auth_url:
            st.info("Click the button below to authenticate with your Google account")
            st.markdown(f"""
                <a href='{auth_url}' target='_blank'>
                    <button style='padding: 8px 16px; background-color: #FF4B4B; color: white; border: none; border-radius: 4px; cursor: pointer;'>
                        Sign in with Google
                    </button>
                </a>
            """, unsafe_allow_html=True)
        return

    # If service exists but email not set, get user profile
    if not st.session_state.logged_in_email:
        try:
            profile = service.users().getProfile(userId='me').execute()
            st.session_state.logged_in_email = profile['emailAddress']
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Error getting user profile: {str(e)}")
            return

    # Display emails
    emails, next_page_token = fetch_emails(service, max_results=10, page_token=st.session_state.page_token)
    
    if emails:
        for email in emails:
            with st.expander(f"📧 {email['subject']} - {email['from']}"):
                st.write(f"**From:** {email['from']}")
                st.write(f"**Subject:** {email['subject']}")
                st.write("**Body:**")
                st.components.v1.html(email['body'], height=600, scrolling=True)

                if email['images']:
                    st.write("📷 **Inline Images:**")
                    for content_id, image_data in email['images'].items():
                        st.image(image_data, caption=f"Embedded Image: {content_id}", use_column_width=True)

        # Pagination controls
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Previous Page") and st.session_state.page_token:
                st.session_state.page_token = None
                st.experimental_rerun()
        with col2:
            if next_page_token and st.button("Next Page"):
                st.session_state.page_token = next_page_token
                st.experimental_rerun()

if __name__ == "__main__":
    main()
