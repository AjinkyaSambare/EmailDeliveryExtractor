import streamlit as st
import os
import pickle
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
from urllib.parse import parse_qs, urlparse

# Google API Scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

st.title("📧 Email - Extractor")

# Global session state variables
if "logged_in_email" not in st.session_state:
    st.session_state.logged_in_email = None
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "oauth_state" not in st.session_state:
    st.session_state.oauth_state = None

def authenticate_user():
    """Authenticate user using Google OAuth and store credentials securely."""
    creds = None

    # Load stored credentials if available
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    # If credentials are invalid or expired, refresh or request new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Check if we have a code in the URL query parameters
            query_params = st.experimental_get_query_params()
            code = query_params.get("code", [None])[0]
            state = query_params.get("state", [None])[0]

            if code and state:
                try:
                    # Recreate the flow with the stored state
                    flow = Flow.from_client_config(
                        st.secrets["google_client_config"],
                        scopes=SCOPES,
                        redirect_uri=st.secrets["redirect_uri"],
                        state=state
                    )
                    
                    # Exchange the authorization code for credentials
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                    
                    # Save the credentials for future sessions
                    with open("token.pickle", "wb") as token:
                        pickle.dump(creds, token)
                    
                    # Clear the URL parameters
                    st.experimental_set_query_params()
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
                    return None
            else:
                # Create the flow using the client secrets
                flow = Flow.from_client_config(
                    st.secrets["google_client_config"],
                    scopes=SCOPES,
                    redirect_uri=st.secrets["redirect_uri"]
                )

                # Generate the authorization URL
                auth_url, state = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true'
                )

                # Store the state in session state
                st.session_state.oauth_state = state

                # Create the authorization URL button
                st.markdown(f'''
                    <a href="{auth_url}" target="_blank">
                        <button style="background-color: #4CAF50; color: white; padding: 12px 20px; 
                        border: none; border-radius: 4px; cursor: pointer;">
                            Sign in with Google
                        </button>
                    </a>
                ''', unsafe_allow_html=True)
                return None

    return build('gmail', 'v1', credentials=creds) if creds else None

def decode_email_body(payload):
    """Decode the email body and extract inline images."""
    body = ""
    images = {}

    if 'parts' in payload:
        for part in payload['parts']:
            content_type = part['mimeType']
            if content_type == 'text/html':
                body = base64.urlsafe_b64decode(part['body']['data']).decode("utf-8")
            elif content_type.startswith('image/') and 'filename' in part:
                image_data = base64.urlsafe_b64decode(part['body']['data'])
                content_id = part['headers'][0]['value'].strip('<>')
                images[content_id] = image_data

    else:
        body = base64.urlsafe_b64decode(payload['body']['data']).decode("utf-8") if 'data' in payload['body'] else "No message content."

    return body.strip(), images

def fetch_emails(service, max_results=10, page_token=None):
    """Fetch emails from Gmail API."""
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

# User Authentication
service = authenticate_user()
if service and not st.session_state.logged_in_email:
    user_profile = service.users().getProfile(userId='me').execute()
    st.session_state.logged_in_email = user_profile['emailAddress']
    st.session_state.page_token = None
    st.experimental_rerun()

if st.session_state.logged_in_email:
    st.success(f"Logged in as: {st.session_state.logged_in_email}")
    if st.button("Log out"):
        if os.path.exists("token.pickle"):
            os.remove("token.pickle")
        st.session_state.logged_in_email = None
        st.session_state.page_token = None
        st.session_state.oauth_state = None
        st.experimental_rerun()

    # Display Emails
    service = authenticate_user()
    if service:
        emails, next_page_token = fetch_emails(service, max_results=10, page_token=st.session_state.page_token)

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

        # Pagination buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Previous Page") and st.session_state.page_token is not None:
                st.session_state.page_token = None
        with col2:
            if next_page_token:
                if st.button("Next Page"):
                    st.session_state.page_token = next_page_token
