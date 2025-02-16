import streamlit as st
import os
import pickle
import base64
import json
import uuid
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Configure page settings - must be the first Streamlit command
st.set_page_config(page_title="Email Extractor", page_icon="📧", layout="wide")

# Google API Scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Initialize session states
if "page" not in st.session_state:
    st.session_state.page = "login"
if "credentials" not in st.session_state:
    st.session_state.credentials = None
if "logged_in_email" not in st.session_state:
    st.session_state.logged_in_email = None
if "page_token" not in st.session_state:
    st.session_state.page_token = None

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
            except Exception:
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
        results = service.users().messages().list(userId='me', maxResults=max_results, pageToken=page_token).execute()
        messages = results.get('messages', [])
        next_page_token = results.get('nextPageToken')
        email_list = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload']['headers']
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), "No Subject")
            sender = next((header['value'] for header in headers if header['name'] == 'From'), "Unknown Sender")
            body, images = decode_email_body(msg_data['payload'])
            email_list.append({"subject": subject, "from": sender, "body": body, "images": images})
        return email_list, next_page_token
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return [], None

def authenticate_user():
    """Authenticate user using Google OAuth and store credentials securely."""
    creds = st.session_state.get('credentials')
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    
    query_params = st.experimental_get_query_params()
    if "code" in query_params and "state" in query_params and query_params["state"][0] == st.session_state.auth_state:
        try:
            client_config = {
                "web": st.secrets["google_client_config"]
            }
            flow = Flow.from_client_config(client_config, SCOPES, redirect_uri=client_config["web"]["redirect_uris"][0])
            flow.fetch_token(code=query_params["code"][0])
            creds = flow.credentials
            st.session_state.credentials = creds
            st.session_state.logged_in_email = creds.id_token['email']
            st.session_state.page = "emails"
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            st.error(f"Error completing authentication: {str(e)}")
            return None
    elif "error" in query_params:
        st.error("Access denied or session expired")
        return None
    else:
        state = str(uuid.uuid4())
        client_config = {
            "web": st.secrets["google_client_config"]
        }
        flow = Flow.from_client_config(client_config, SCOPES, redirect_uri=client_config["web"]["redirect_uris"][0])
        auth_url, _ = flow.authorization_url(prompt="consent", state=state, access_type="offline")
        st.session_state.auth_state = state
        st.markdown(f'<a href="{auth_url}" target="_self">Authenticate with Google</a>', unsafe_allow_html=True)
        return None

def show_emails_page():
    """Display the emails page with Gmail content."""
    service = authenticate_user()
    if service:
        user_profile = service.users().getProfile(userId='me').execute()
        st.success(f"Logged in as: {user_profile['emailAddress']}")
        emails, next_page_token = fetch_emails(service, page_token=st.session_state.page_token)
        for email in emails:
            with st.expander(f"📧 {email['subject']} - {email['from']}"):
                st.markdown(f"**From:** {email['from']}\n**Subject:** {email['subject']}")
                st.components.v1.html(email['body'], height=600, scrolling=True)
                if email['images']:
                    for content_id, image_data in email['images'].items():
                        st.image(image_data, caption=f"Embedded Image: {content_id}", use_column_width=True)
        if st.button("Previous Page") and st.session_state.page_token:
            st.session_state.page_token = None
        if next_page_token and st.button("Next Page"):
            st.session_state.page_token = next_page_token

def show_login_page():
    """Display the login page."""
    st.title("📧 Email - Extractor")
    st.markdown("Connect to your Gmail account to extract and view your emails.")
    authenticate_user()

# Main page router
if st.session_state.page == "login":
    show_login_page()
elif st.session_state.page == "emails":
    show_emails_page()
