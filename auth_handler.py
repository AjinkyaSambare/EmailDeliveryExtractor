import streamlit as st
from googleapiclient.discovery import build

def get_auth_code_from_url():
    """Extract authorization code from URL if present."""
    try:
        query_params = st.experimental_get_query_params()
        if 'code' in query_params:
            return query_params['code'][0]
    except:
        return None
    return None

def create_gmail_service(credentials):
    """Create and return a Gmail service object."""
    try:
        return build('gmail', 'v1', credentials=credentials)
    except Exception as e:
        st.error(f"Error creating Gmail service: {str(e)}")
        return None

def get_client_config():
    """Return the Google client configuration from secrets."""
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