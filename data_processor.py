import streamlit as st
import requests
import json
import base64
from datetime import datetime
import pytz
import pandas as pd
from typing import Dict, Any, List
from database import insert_into_db

class AzureOpenAIChat:
    def __init__(self):
        """Initialize API credentials from Streamlit secrets."""
        self.API_ENDPOINT = st.secrets.get("AZURE_OPENAI_API_ENDPOINT", "")
        self.API_KEY = st.secrets.get("AZURE_OPENAI_API_KEY", "")

    def extract_delivery_details(self, email_body: str, max_tokens: int = 300) -> Dict[str, Any]:
        """Send an email body to Azure OpenAI and extract structured delivery-related details."""
        headers = {
            "Content-Type": "application/json",
            "api-key": self.API_KEY,
        }

        prompt = f"""
        Extract delivery-related details from the following email body and return a JSON output with these keys:
        - delivery: "yes" if delivery is confirmed, otherwise "no".
        - price_num: Extracted price amount, default to 0.00 if not found.
        - description: Short description of the product if available.
        - order_id: Extracted order ID if available.
        - delivery_date: Extracted delivery date in YYYY-MM-DD format if available.
        - store: Store or sender name.
        - tracking_number: Extracted tracking number if available.
        - carrier: Extracted carrier name (FedEx, UPS, USPS, etc.) if available.

        Email Body:
        {email_body}

        Output JSON:
        """

        data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.5,
            "top_p": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        }

        try:
            response = requests.post(self.API_ENDPOINT, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error calling Azure OpenAI API: {str(e)}")
            return None

def is_delivery_related(subject, snippet):
    """Check if the email is delivery-related based on more precise keyword matching."""
    text = (subject + ' ' + snippet).lower()
    
    # Common false positive words that should be excluded
    exclusion_words = ['certificate', 'training', 'course', 'class', 'workshop', 'webinar']
    
    # If any exclusion word is present, check if it's actually not a delivery context
    for word in exclusion_words:
        if word in text:
            return False
            
    # Check for delivery-specific word combinations
    delivery_patterns = [
        ('order', ['shipped', 'delivered', 'delivery', 'arriving', 'tracking']),
        ('package', ['delivered', 'arrival', 'tracking', 'shipped']),
        ('shipping', ['status', 'update', 'confirmation', 'tracking']),
        ('delivery', ['scheduled', 'attempted', 'successful', 'status']),
        ('tracking', ['number', 'status', 'update', 'information']),
    ]
    
    # Check for courier service names
    courier_services = ['fedex', 'ups', 'usps', 'dhl', 'amazon delivery']
    if any(service in text for service in courier_services):
        return True
    
    # Check for delivery-specific patterns
    for main_word, related_words in delivery_patterns:
        if main_word in text:
            if any(related in text for related in related_words):
                return True
    
    # Additional specific phrases that indicate delivery
    specific_phrases = [
        'out for delivery',
        'will be delivered',
        'has been delivered',
        'delivery notification',
        'shipment notification',
        'delivery status',
        'shipping confirmation',
        'arriving',
        'package arrival'
    ]
    
    return any(phrase in text for phrase in specific_phrases)

def get_email_messages(service, max_results=100):
    """Fetch and process delivery-related emails with detailed progress tracking."""
    try:
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        status_text.text("📥 Fetching emails from Gmail...")
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            status_text.info("No messages found in the inbox.")
            return []
            
        email_data = []
        chat_client = AzureOpenAIChat()
        total_messages = len(messages)
        
        status_text.text(f"🔍 Found {total_messages} emails to analyze")
        
        for idx, message in enumerate(messages):
            # Update progress
            progress = int((idx + 1) * 100 / total_messages)
            progress_bar.progress(progress)
            
            try:
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                headers = msg['payload']['headers']
                
                subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
                sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
                date_str = next((header['value'] for header in headers if header['name'].lower() == 'date'), '')
                snippet = msg.get('snippet', 'No preview available')
                
                # Only process delivery-related emails
                if is_delivery_related(subject, snippet):
                    status_text.text(f"📦 Processing delivery email {idx + 1}/{total_messages}: {subject}")
                    
                    try:
                        date_obj = datetime.strptime(date_str.split(' (')[0].strip(), '%a, %d %b %Y %H:%M:%S %z')
                        formatted_date = date_obj.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
                    except:
                        formatted_date = date_str
                    
                    # Extract full email body
                    email_body = ""
                    if 'parts' in msg['payload']:
                        for part in msg['payload']['parts']:
                            if part['mimeType'] == 'text/plain':
                                body_data = part.get('body', {}).get('data', '')
                                if body_data:
                                    email_body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                    else:
                        body_data = msg['payload'].get('body', {}).get('data', '')
                        if body_data:
                            email_body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                    
                    # Process through GPT
                    response = chat_client.extract_delivery_details(f"Subject: {subject}\n\nBody: {snippet}\n\n{email_body}")
                    if response and "choices" in response:
                        try:
                            extracted_text = response["choices"][0]["message"]["content"]
                            # Clean up the JSON string
                            extracted_text = extracted_text.strip()
                            if extracted_text.startswith("```json"):
                                extracted_text = extracted_text[7:-3]  # Remove ```json and ``` markers
                            
                            parsed_json = json.loads(extracted_text)
                            # Add email metadata
                            parsed_json['email_id'] = message['id']
                            parsed_json['subject'] = subject
                            parsed_json['sender'] = sender
                            parsed_json['date'] = formatted_date
                            email_data.append(parsed_json)
                            
                            # Store in database
                            insert_into_db(parsed_json, message['id'])
                        except json.JSONDecodeError as e:
                            st.warning(f"Failed to parse response for email: {subject}\nError: {str(e)}")
                            continue
            except Exception as e:
                st.warning(f"Error processing email {subject}: {str(e)}")
                continue
        
        status_text.text(f"✅ Completed processing {len(email_data)} delivery emails")
        progress_bar.progress(100)
        return email_data
        
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return []

def display_delivery_details(data: Dict[str, Any]):
    """Display delivery details in a formatted table."""
    try:
        col1, col2 = st.columns(2)

        with col1:
            status_color = "success" if data.get("delivery") == "yes" else "error"
            st.markdown(
                f"""
                <div style='background-color: {'#28a745' if status_color == 'success' else '#dc3545'};
                          padding: 10px;
                          border-radius: 5px;
                          color: white;
                          display: inline-block;
                          margin-bottom: 10px;'>
                    {'✓ Delivery Confirmed' if data.get("delivery") == "yes" else '⚠ Delivery Not Confirmed'}
                </div>
                """,
                unsafe_allow_html=True
            )

        with col2:
            if data.get("price_num", 0) > 0:
                st.markdown(f"### 💰 ${data['price_num']:.2f}")

        details_dict = {
            "Field": [
                "Subject",
                "Sender",
                "Date",
                "Order ID",
                "Description",
                "Store",
                "Delivery Date",
                "Carrier",
                "Tracking Number"
            ],
            "Value": [
                data.get("subject", ""),
                data.get("sender", ""),
                data.get("date", ""),
                data.get("order_id", ""),
                data.get("description", ""),
                data.get("store", ""),
                data.get("delivery_date", ""),
                data.get("carrier", ""),
                data.get("tracking_number", "")
            ]
        }

        df = pd.DataFrame(details_dict)
        st.dataframe(
            df,
            hide_index=True,
            column_config={
                "Field": st.column_config.Column(width="medium"),
                "Value": st.column_config.Column(width="large")
            }
        )

        if data.get("tracking_number") and data.get("carrier"):
            st.info(f"💡 You can track your package using the tracking number: {data['tracking_number']}")

    except Exception as e:
        st.error(f"Error displaying delivery details: {str(e)}")