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

def get_email_messages(service, max_results=100):
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
    
    # Debug info
    st.sidebar.write("Debug Info:")
    st.sidebar.write(f"Auth Code Present: {bool(auth_code)}")
    st.sidebar.write(f"Auth in Progress: {st.session_state.auth_in_progress}")
    st.sidebar.write(f"Has Credentials: {bool(st.session_state.credentials)}")
    
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
