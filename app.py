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

def authenticate_user():
    """Authenticate user using Google OAuth and store credentials securely."""
    creds = st.session_state.get('credentials')

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            st.session_state.credentials = creds
        else:
            # Check for OAuth state and code in URL parameters
            query_params = st.experimental_get_query_params()
            
            if "code" in query_params:
                try:
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
                    
                    flow.fetch_token(code=query_params["code"][0])
                    creds = flow.credentials
                    st.session_state.credentials = creds
                    st.session_state.page = "emails"  # Switch to emails page after auth
                    return build('gmail', 'v1', credentials=creds)
                except Exception as e:
                    st.error(f"Error completing authentication: {str(e)}")
                    return None
            else:
                try:
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
                    
                    auth_url, _ = flow.authorization_url(
                        access_type='offline',
                        include_granted_scopes='true',
                        prompt='consent'
                    )
                    
                    st.info("Click the button below to authenticate with your Google account")
                    st.markdown(f'''
                        <a href="{auth_url}" target="_self">
                            <button style="
                                background-color: #4285f4;
                                color: white;
                                padding: 10px 20px;
                                border: none;
                                border-radius: 4px;
                                font-size: 16px;
                                cursor: pointer;
                                display: flex;
                                align-items: center;
                                gap: 10px;
                            ">
                                <svg style="width: 24px; height: 24px;" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
                                    <path fill="#FFC107" d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12s5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24s8.955,20,20,20s20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z"/>
                                    <path fill="#FF3D00" d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z"/>
                                    <path fill="#4CAF50" d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z"/>
                                    <path fill="#1976D2" d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z"/>
                                </svg>
                                Sign in with Google
                            </button>
                        </a>
                    ''', unsafe_allow_html=True)
                    return None
                except Exception as e:
                    st.error(f"Error initiating authentication: {str(e)}")
                    return None

    return build('gmail', 'v1', credentials=creds)

def show_emails_page():
    """Display the emails page with Gmail content."""
    st.title("📧 Your Emails")
    
    service = authenticate_user()
    if service:
        try:
            user_profile = service.users().getProfile(userId='me').execute()
            st.success(f"Logged in as: {user_profile['emailAddress']}")
            
            if st.button("Log out"):
                st.session_state.credentials = None
                st.session_state.logged_in_email = None
                st.session_state.page = "login"
                st.session_state.page_token = None
                st.experimental_rerun()
            
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
                    if st.button("Previous Page") and st.session_state.page_token is not None:
                        st.session_state.page_token = None
                        st.experimental_rerun()
                with col2:
                    if next_page_token and st.button("Next Page"):
                        st.session_state.page_token = next_page_token
                        st.experimental_rerun()
                        
        except Exception as e:
            st.error(f"Error loading emails: {str(e)}")
            st.session_state.page = "login"
            st.experimental_rerun()

def show_login_page():
    """Display the login page."""
    st.title("📧 Email - Extractor")
    st.write("Connect to your Gmail account to extract and view your emails.")
    
    service = authenticate_user()
    if service:
        st.session_state.page = "emails"
        st.experimental_rerun()

# Main page router
if st.session_state.page == "login":
    show_login_page()
elif st.session_state.page == "emails":
    show_emails_page()
