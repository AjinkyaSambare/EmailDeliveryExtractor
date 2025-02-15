import streamlit as st
import os
import pickle
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# OAuth2 Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Streamlit UI Title
st.title("Email - Extractor")

# Initialize session state for user login status and pagination token
if "logged_in_email" not in st.session_state:
    st.session_state.logged_in_email = None
if "page_token" not in st.session_state:
    st.session_state.page_token = None

def authenticate_user():
    creds = None
    token_path = "token.pickle"
    # Fetch the client secrets from Streamlit secrets (stored in TOML format)
    client_secret_info = st.secrets["google_client_config"]
    # This dictionary structure is required by Google's OAuth client library
    client_config = {"web": client_secret_info}
    redirect_uri = client_secret_info["redirect_uris"][0]

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                client_config, SCOPES, redirect_uri=redirect_uri)
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.write(f"Please go to this URL and authorize access: {auth_url}")
            code = st.text_input("Enter the authorization code")
            if code:
                flow.fetch_token(code=code)
                creds = flow.credentials
                with open(token_path, "wb") as token:
                    pickle.dump(creds, token)
    return build('gmail', 'v1', credentials=creds)

def decode_email_body(payload):
    body = ""
    if 'parts' in payload:
        for part in payload['parts']:
            body_data = part['body'].get('data')
            if body_data:
                body += base64.urlsafe_b64decode(body_data).decode("utf-8")
    else:
        body_data = payload.get('body', {}).get('data')
        if body_data:
            body = base64.urlsafe_b64decode(body_data).decode("utf-8")
    return body.strip()

def fetch_emails(service, max_results=10, page_token=None):
    results = service.users().messages().list(userId='me', maxResults=max_results, pageToken=page_token).execute()
    messages = results.get('messages', [])
    next_page_token = results.get('nextPageToken')

    email_list = []
    if messages:
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload']['headers']
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), "No Subject")
            sender = next((header['value'] for header in headers if header['name'] == 'From'), "Unknown Sender")
            body = decode_email_body(msg_data['payload'])

            email_list.append({"subject": subject, "from": sender, "body": body})

    return email_list, next_page_token

# Main app logic
if not st.session_state.logged_in_email:
    if st.button("Sign in with Google"):
        service = authenticate_user()
        user_profile = service.users().getProfile(userId='me').execute()
        st.session_state.logged_in_email = user_profile['emailAddress']
        st.session_state.page_token = None  # Reset pagination
else:
    st.success(f"Logged in as: {st.session_state.logged_in_email}")
    if st.button("Log out"):
        if os.path.exists("token.pickle"):
            os.remove("token.pickle")
        st.session_state.logged_in_email = None
        st.session_state.page_token = None  # Reset pagination

if st.session_state.logged_in_email:
    service = authenticate_user()
    emails, next_page_token = fetch_emails(service, page_token=st.session_state.page_token)

    if emails:
        for email in emails:
            with st.expander(f"{email['subject']} - {email['from']}"):
                st.write(f"**From:** {email['from']}")
                st.write(f"**Subject:** {email['subject']}")
                st.write("**Body:**")
                st.write(email['body'])

    if next_page_token:
        if st.button("Load more"):
            st.session_state.page_token = next_page_token
