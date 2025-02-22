import streamlit as st
from auth_handler import get_auth_code_from_url, create_gmail_service, get_client_config
from google_auth_oauthlib.flow import Flow
from data_processor import get_email_messages, display_delivery_details
from database import (
    create_table_if_not_exists, 
    get_delivery_history, 
    display_history_table,
    get_processing_statistics
)

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
        # Process emails
        service = create_gmail_service(st.session_state.credentials)
        if service:
            processed_emails = get_email_messages(service)
            
            # Display results
            if processed_emails:
                st.success(f"✅ Successfully processed {len(processed_emails)} delivery-related emails")
                
                # Statistics
                st.markdown("### 📊 Processing Statistics")
                stats = get_processing_statistics()
                stat_col1, stat_col2, stat_col3 = st.columns(3)

                with stat_col1:
                    st.metric("Total Emails Processed", stats["total_emails"])
                with stat_col2:
                    st.metric("Confirmed Deliveries", stats["confirmed_deliveries"])
                with stat_col3:
                    st.metric("Total Value", f"${stats['total_value']:.2f}")
                
                # Display detailed results
                st.markdown("### 📦 Recent Deliveries")
                for email in processed_emails:
                    expander_title = f"📧 {email.get('subject', '')} - From: {email.get('sender', '')}"
                    with st.expander(expander_title):
                        display_delivery_details(email)
                        
            # Display historical data
            st.markdown("---")
            display_history_table(get_delivery_history())
            st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                button_col1, button_col2 = st.columns(2)
                with button_col1:
                    if st.button("🔄 Refresh", use_container_width=True):
                        st.rerun()
                with button_col2:
                    if st.button("🚪 Logout", key="logout_bottom", use_container_width=True):
                        for key in list(st.session_state.keys()):
                            del st.session_state[key]
                        st.rerun()

if __name__ == "__main__":
    # Initialize session states
    st.session_state.setdefault('credentials', None)
    st.session_state.setdefault('auth_in_progress', False)
    st.session_state.setdefault('auth_code', None)
    st.session_state.setdefault('processed_emails', [])
    st.session_state.setdefault('total_emails', 0)
    st.session_state.setdefault('current_progress', 0)
    main()