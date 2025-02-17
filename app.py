import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime
import pytz
from urllib.parse import urlparse, parse_qs

# Initialize session states
if 'credentials' not in st.session_state:
    st.session_state.credentials = None
if 'auth_in_progress' not in st.session_state:
    st.session_state.auth_in_progress = False

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

def get_email_messages(service, max_results=50):
    try:
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            st.info("No messages found in the inbox.")
            return []
            
        email_data = []
        with st.spinner('Loading emails...'):
            for message in messages:
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                headers = msg['payload']['headers']
                
                subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
                sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
                date_str = next((header['value'] for header in headers if header['name'].lower() == 'date'), '')
                
                try:
                    date_obj = datetime.strptime(date_str.split(' (')[0].strip(), '%a, %d %b %Y %H:%M:%S %z')
                    formatted_date = date_obj.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
                except:
                    formatted_date = date_str
                    
                email_data.append({
                    'subject': subject,
                    'sender': sender,
                    'date': formatted_date,
                    'snippet': msg.get('snippet', 'No preview available')
                })
        return email_data
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return []

def main():
    st.set_page_config(page_title="Gmail Inbox Viewer", page_icon="📧", layout="wide")
    st.title("📧 Gmail Inbox Viewer")

    # Check for authorization code in URL
    auth_code = get_auth_code_from_url()
    
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
                st.experimental_rerun()
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
            st.experimental_rerun()
        
        # Display emails
        service = create_gmail_service(st.session_state.credentials)
        if service:
            emails = get_email_messages(service)
            if emails:
                st.subheader("Your Inbox")
                
                # Search and filter options
                col1, col2 = st.columns([3, 1])
                with col1:
                    search_term = st.text_input("Search emails", "").lower()
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

if __name__ == "__main__":
    main()

# import streamlit as st
# import os
# import pickle
# import base64
# import json
# from google_auth_oauthlib.flow import Flow
# from google.auth.transport.requests import Request
# from googleapiclient.discovery import build

# # Configure page settings - must be the first Streamlit command
# st.set_page_config(page_title="Email Extractor", page_icon="📧", layout="wide")

# # Google API Scope
# SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# st.title("📧 Email - Extractor")

# # Global session state variables
# if "logged_in_email" not in st.session_state:
#     st.session_state.logged_in_email = None
# if "page_token" not in st.session_state:
#     st.session_state.page_token = None
# if "credentials" not in st.session_state:
#     st.session_state.credentials = None

# def authenticate_user():
#     """Authenticate user using Google OAuth and store credentials securely."""
#     creds = st.session_state.get('credentials')

#     # If credentials are invalid or expired, refresh or request new ones
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             # Check if required secrets are configured
#             if "google_client_config" not in st.secrets:
#                 st.error("Google client configuration is missing. Please configure the secrets.")
#                 st.stop()

#             config = st.secrets["google_client_config"]
#             required_keys = ["client_id", "client_secret", "redirect_uris"]
#             missing_keys = [key for key in required_keys if key not in config]
            
#             if missing_keys:
#                 st.error(f"Missing required configuration: {', '.join(missing_keys)}")
#                 st.stop()

#             # Get the first redirect URI from the array
#             redirect_uri = config["redirect_uris"][0]

#             # Load client secrets from Streamlit secrets exactly as provided
#             client_config = {
#                 "web": {
#                     "client_id": config["client_id"],
#                     "project_id": config["project_id"],
#                     "auth_uri": config["auth_uri"],
#                     "token_uri": config["token_uri"],
#                     "auth_provider_x509_cert_url": config["auth_provider_x509_cert_url"],
#                     "client_secret": config["client_secret"],
#                     "redirect_uris": config["redirect_uris"]
#                 }
#             }
            
#             flow = Flow.from_client_config(
#                 client_config,
#                 scopes=SCOPES,
#                 redirect_uri=redirect_uri
#             )
            
#             # Generate authorization URL with offline access
#             auth_url, _ = flow.authorization_url(
#                 access_type='offline',
#                 include_granted_scopes='true'
#             )
            
#             # Display the auth URL to the user with clear instructions
#             st.info("Click the button below to authenticate with your Google account")
#             st.markdown(f"<a href='{auth_url}' target='_blank'><button style='padding: 8px 16px; background-color: #FF4B4B; color: white; border: none; border-radius: 4px; cursor: pointer;'>Sign in with Google</button></a>", unsafe_allow_html=True)
#             return None  # Return None to handle the callback in the main flow

#     return build('gmail', 'v1', credentials=creds)

# def decode_email_body(payload):
#     """Decode the email body and extract inline images."""
#     body = ""
#     images = {}

#     if 'parts' in payload:
#         for part in payload['parts']:
#             try:
#                 content_type = part['mimeType']
#                 if content_type == 'text/html':
#                     body = base64.urlsafe_b64decode(part['body']['data']).decode("utf-8")
#                 elif content_type.startswith('image/') and 'filename' in part:
#                     image_data = base64.urlsafe_b64decode(part['body']['data'])
#                     content_id = part.get('headers', [{'value': 'unknown'}])[0]['value'].strip('<>')
#                     images[content_id] = image_data
#             except Exception as e:
#                 st.warning(f"Error decoding part: {str(e)}")
#                 continue
#     else:
#         try:
#             body = base64.urlsafe_b64decode(payload['body']['data']).decode("utf-8")
#         except Exception:
#             body = "Could not decode message content."

#     return body.strip(), images

# def fetch_emails(service, max_results=10, page_token=None):
#     """Fetch emails from Gmail API."""
#     try:
#         if page_token:
#             results = service.users().messages().list(
#                 userId='me', 
#                 maxResults=max_results, 
#                 pageToken=page_token
#             ).execute()
#         else:
#             results = service.users().messages().list(
#                 userId='me', 
#                 maxResults=max_results
#             ).execute()

#         messages = results.get('messages', [])
#         next_page_token = results.get('nextPageToken')
#         email_list = []

#         with st.spinner('Fetching emails...'):
#             for msg in messages:
#                 msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
#                 headers = msg_data['payload']['headers']
#                 subject = next((header['value'] for header in headers if header['name'] == 'Subject'), "No Subject")
#                 sender = next((header['value'] for header in headers if header['name'] == 'From'), "Unknown Sender")

#                 body, images = decode_email_body(msg_data['payload'])
#                 email_list.append({
#                     "subject": subject,
#                     "from": sender,
#                     "body": body,
#                     "images": images
#                 })

#         return email_list, next_page_token
#     except Exception as e:
#         st.error(f"Error fetching emails: {str(e)}")
#         return [], None

# # Main App Layout
# st.write("Connect to your Gmail account to extract and view your emails.")

# # User Authentication
# if not st.session_state.logged_in_email:
#     if st.button("Sign in with Google"):
#         service = authenticate_user()
#         if service:
#             try:
#                 user_profile = service.users().getProfile(userId='me').execute()
#                 st.session_state.logged_in_email = user_profile['emailAddress']
#                 st.session_state.page_token = None
#             except Exception as e:
#                 st.error(f"Error getting user profile: {str(e)}")
# else:
#     st.success(f"Logged in as: {st.session_state.logged_in_email}")
#     if st.button("Log out"):
#         st.session_state.logged_in_email = None
#         st.session_state.credentials = None
#         st.session_state.page_token = None
#         st.experimental_rerun()

# # Display Emails
# if st.session_state.logged_in_email:
#     service = authenticate_user()
#     if service:
#         emails, next_page_token = fetch_emails(service, max_results=10, page_token=st.session_state.page_token)

#         if emails:
#             for email in emails:
#                 with st.expander(f"📧 {email['subject']} - {email['from']}"):
#                     st.write(f"**From:** {email['from']}")
#                     st.write(f"**Subject:** {email['subject']}")
#                     st.write("**Body:**")
#                     st.components.v1.html(email['body'], height=600, scrolling=True)

#                     if email['images']:
#                         st.write("📷 **Inline Images:**")
#                         for content_id, image_data in email['images'].items():
#                             st.image(image_data, caption=f"Embedded Image: {content_id}", use_column_width=True)

#             # Pagination controls
#             col1, col2 = st.columns(2)
#             with col1:
#                 if st.button("Previous Page") and st.session_state.page_token is not None:
#                     st.session_state.page_token = None
#             with col2:
#                 if next_page_token and st.button("Next Page"):
#                     st.session_state.page_token = next_page_token