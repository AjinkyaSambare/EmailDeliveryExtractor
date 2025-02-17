import streamlit as st
import base64
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Configure page settings
st.set_page_config(page_title="Email Extractor - Emails", page_icon="📧", layout="wide")

# Initialize session state
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "logged_in_email" not in st.session_state:
    st.session_state.logged_in_email = None

st.title("📧 Your Emails")

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

def main():
    service = get_google_service()
    
    # Show logout button if logged in
    if st.session_state.logged_in_email:
        st.success(f"Logged in as: {st.session_state.logged_in_email}")
        if st.button("Log out"):
            st.session_state.clear()
            st.switch_page("pages/1_🏠_Home.py")
    
    # If not authenticated, redirect to home page
    if not service:
        st.warning("Please sign in first")
        st.switch_page("pages/1_🏠_Home.py")
        return

    # If service exists but email not set, get user profile
    if not st.session_state.logged_in_email:
        try:
            profile = service.users().getProfile(userId='me').execute()
            st.session_state.logged_in_email = profile['emailAddress']
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Error getting user profile: {str(e)}")
            st.switch_page("pages/1_🏠_Home.py")
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
