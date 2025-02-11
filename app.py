import streamlit as st
import os
import pickle
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

st.title("Email - Extractor")

# Global variables to store session state
if "logged_in_email" not in st.session_state:
    st.session_state.logged_in_email = None
if "page_token" not in st.session_state:
    st.session_state.page_token = None


def authenticate_user():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return build('gmail', 'v1', credentials=creds)


def decode_email_body(payload):
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
                    content_id = part['headers'][0]['value'].strip('<>')
                    images[content_id] = image_data
            except Exception as e:
                continue
    else:
        try:
            body = base64.urlsafe_b64decode(payload['body']['data']).decode("utf-8")
        except Exception as e:
            body = "Could not decode message content."

    return body.strip(), images


def fetch_emails(service, max_results=10, page_token=None):
    if page_token:
        results = service.users().messages().list(userId='me', maxResults=max_results, pageToken=page_token).execute()
    else:
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()

    messages = results.get('messages', [])
    next_page_token = results.get('nextPageToken')
    email_list = []

    if messages:
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload']['headers']
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), "No Subject")
            sender = next((header['value'] for header in headers if header['name'] == 'From'), "Unknown Sender")

            body, images = decode_email_body(msg_data['payload'])

            email_list.append({"subject": subject, "from": sender, "body": body, "images": images})

    return email_list, next_page_token


# Login and logout logic
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

        # Pagination buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Previous Page") and st.session_state.page_token is not None:
                st.session_state.page_token = None  # Reset to the first page
        with col2:
            if next_page_token:
                if st.button("Next Page"):
                    st.session_state.page_token = next_page_token
            else:
                st.info("No more emails to show.")  # End of inbox