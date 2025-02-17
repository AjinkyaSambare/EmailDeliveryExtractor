# Home.py (main file)
import streamlit as st
from google_auth_oauthlib.flow import Flow
import pickle
import os

# Configure page settings
st.set_page_config(page_title="Email Extractor - Login", page_icon="🏠", layout="wide")

# Initialize session state
if "credentials" not in st.session_state:
    st.session_state.credentials = None

st.title("📧 Email Extractor - Login")

# Google API Scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def setup_google_oauth():
    """Setup Google OAuth flow."""
    if "google_client_config" not in st.secrets:
        st.error("Google client configuration is missing.")
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
    
    # Use the production Streamlit URL with correct page path
    redirect_uri = "https://emaildelivery.streamlit.app/Email_Display"  # Match the filename
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    return auth_url

def main():
    st.write("Welcome to Email Extractor! Please sign in with your Google account to continue.")
    
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

if __name__ == "__main__":
    main()