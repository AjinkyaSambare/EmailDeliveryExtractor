from time import sleep
import streamlit as st
from google_auth_oauthlib.flow import Flow
from auth_handler import create_gmail_service, get_client_config
from data_processor import get_email_messages, display_delivery_details
from database import (
    create_table_if_not_exists,
    get_delivery_history,
    display_history_table,
    get_processing_statistics,
    clear_all_records
)

def get_auth_code_from_url():
    """Extract the authorization code from URL parameters"""
    params = st.query_params
    if 'code' in params:
        return params['code']
    return None

def main():
    st.set_page_config(page_title="Delivery Email Analyzer", page_icon="📦", layout="wide")
    st.title("📦 Delivery Email Analyzer")

    # Create database table if it doesn't exist
    create_table_if_not_exists()

    # Check for authorization code in URL
    auth_code = get_auth_code_from_url()
    
    if auth_code and not st.session_state.credentials:
        with st.spinner("🔐 Completing authentication..."):
            try:
                flow = Flow.from_client_config(
                    get_client_config(),
                    scopes=['https://www.googleapis.com/auth/gmail.readonly'],
                    redirect_uri=st.secrets["google_client_config"]["redirect_uris"][0]
                )
                flow.fetch_token(code=auth_code)
                st.session_state.credentials = flow.credentials
                st.session_state.auth_in_progress = False
                st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
                st.session_state.auth_in_progress = False

    # Main content area
    if not st.session_state.credentials:
        st.markdown("""
        ### 🔐 Gmail Authentication Required
        Please login to access your Gmail inbox and analyze delivery emails.
        """)
        auth_col1, auth_col2 = st.columns([1, 2])
        with auth_col1:
            if st.button("🔑 Login with Gmail", key="login", use_container_width=True):
                try:
                    flow = Flow.from_client_config(
                        get_client_config(),
                        scopes=['https://www.googleapis.com/auth/gmail.readonly'],
                        redirect_uri=st.secrets["google_client_config"]["redirect_uris"][0]
                    )
                    auth_url, _ = flow.authorization_url(prompt='consent')
                    st.session_state.auth_in_progress = True
                    st.markdown(f"[Click here to authorize]({auth_url})")
                except Exception as e:
                    st.error(f"Error initiating authentication: {str(e)}")
                    st.session_state.auth_in_progress = False
    else:
        # Show current statistics first
        stats = get_processing_statistics()
        st.markdown("### 📊 Processing Statistics")
        stat_col1, stat_col2, stat_col3 = st.columns(3)
        with stat_col1:
            st.metric("Total Emails Processed", stats["total_emails"])
        with stat_col2:
            st.metric("Confirmed Deliveries", stats["confirmed_deliveries"])
        with stat_col3:
            st.metric("Total Value", f"${stats['total_value']:.2f}")

        # Add Process Emails button
        if st.button("📥 Process New Emails", type="primary", use_container_width=True):
            service = create_gmail_service(st.session_state.credentials)
            if service:
                processed_emails = get_email_messages(service)
                # Display results
                if processed_emails:
                    st.success(f"✅ Successfully processed {len(processed_emails)} delivery-related emails")
                    # Display detailed results
                    st.markdown("### 📦 Recent Deliveries")
                    for email in processed_emails:
                        expander_title = f"📧 {email.get('subject', '')} - From: {email.get('sender', '')}"
                        with st.expander(expander_title):
                            display_delivery_details(email)
                    st.rerun()  # Refresh to update statistics

        # Display historical data
        st.markdown("---")
        display_history_table(get_delivery_history())
        st.markdown("---")

        # Action buttons at the bottom
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            button_col1, button_col2, button_col3 = st.columns(3)
            with button_col1:
                if st.button("🔄 Refresh", use_container_width=True):
                    st.rerun()
            with button_col2:
                if st.button("🚪 Logout", key="logout_bottom", use_container_width=True):
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
            with button_col3:
                if st.button("🗑️ Clear All", type="secondary", use_container_width=True):
                    if clear_all_records():
                        st.success("All records cleared successfully!")
                        sleep(1)  # Give user time to see the message
                        st.rerun()
                    else:
                        st.error("Failed to clear records")

if __name__ == "__main__":
    # Initialize session states
    st.session_state.setdefault('credentials', None)
    st.session_state.setdefault('auth_in_progress', False)
    st.session_state.setdefault('auth_code', None)
    st.session_state.setdefault('processed_emails', [])
    st.session_state.setdefault('total_emails', 0)
    st.session_state.setdefault('current_progress', 0)
    main()