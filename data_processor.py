import streamlit as st
import requests
import json
import base64
from datetime import datetime
import pytz
import pandas as pd
from typing import Dict, Any, List, Set, Optional
from database import insert_into_db, get_connection
from time import sleep

# Configuration constants
BATCH_SIZE = 10
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 1

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

class EmailProcessor:
    def __init__(self):
        self.chat_client = AzureOpenAIChat()
        self.processed_ids = set()
        self.status_text = st.empty()
        self.progress_bar = st.progress(0)

    def _get_processed_ids(self) -> Set[str]:
        """Fetch IDs of previously processed emails."""
        try:
            conn = get_connection()
            if conn is None:
                return set()
            
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email_id 
                FROM delivery_details 
                WHERE email_id IS NOT NULL
            """)
            
            processed_ids = {row[0] for row in cursor.fetchall()}
            conn.close()
            return processed_ids
        except Exception as e:
            st.error(f"Error fetching processed email IDs: {str(e)}")
            return set()

    def _extract_email_body(self, msg: Dict) -> str:
        """Extract email body from message payload."""
        try:
            if 'parts' in msg['payload']:
                for part in msg['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        body_data = part.get('body', {}).get('data', '')
                        if body_data:
                            return base64.urlsafe_b64decode(body_data).decode('utf-8')
            else:
                body_data = msg['payload'].get('body', {}).get('data', '')
                if body_data:
                    return base64.urlsafe_b64decode(body_data).decode('utf-8')
            return ""
        except Exception as e:
            st.warning(f"Error extracting email body: {str(e)}")
            return ""

    def _is_delivery_related(self, subject: str, snippet: str) -> bool:
        """Check if email is delivery-related."""
        text = f"{subject} {snippet}".lower()
        
        # Exclude non-delivery emails
        if any(word in text for word in ['certificate', 'training', 'course', 'workshop']):
            return False

        # Delivery-related patterns
        delivery_patterns = {
            'order': ['shipped', 'delivered', 'delivery', 'arriving', 'tracking'],
            'package': ['delivered', 'arrival', 'tracking', 'shipped'],
            'shipping': ['status', 'update', 'confirmation', 'tracking'],
            'delivery': ['scheduled', 'attempted', 'successful', 'status'],
            'tracking': ['number', 'status', 'update', 'information']
        }

        # Check courier services
        if any(service in text for service in ['fedex', 'ups', 'usps', 'dhl', 'amazon delivery']):
            return True

        # Check delivery patterns
        for main_word, related_words in delivery_patterns.items():
            if main_word in text and any(word in text for word in related_words):
                return True

        # Check specific phrases
        specific_phrases = [
            'out for delivery', 'will be delivered', 'has been delivered',
            'delivery notification', 'shipment notification', 'arriving'
        ]
        return any(phrase in text for phrase in specific_phrases)

    def _process_email_batch(self, emails: List[Dict]) -> List[Dict]:
        """Process a batch of emails using Azure OpenAI."""
        processed_data = []
        
        for email in emails:
            try:
                response = self.chat_client.extract_delivery_details(
                    f"Subject: {email['subject']}\n\nBody: {email['body']}"
                )
                
                if response and "choices" in response:
                    extracted_text = response["choices"][0]["message"]["content"].strip()
                    if extracted_text.startswith("```json"):
                        extracted_text = extracted_text[7:-3]

                    parsed_json = json.loads(extracted_text)
                    parsed_json.update({
                        'email_id': email['id'],
                        'subject': email['subject'],
                        'sender': email['sender'],
                        'date': self._format_date(email['date'])
                    })
                    
                    processed_data.append(parsed_json)
                    insert_into_db(parsed_json, email['id'])
                    
            except Exception as e:
                st.warning(f"Error processing email {email['subject']}: {str(e)}")
                continue
        
        return processed_data

    def _format_date(self, date_str: str) -> str:
        """Format email date string to UTC datetime."""
        try:
            date_obj = datetime.strptime(date_str.split(' (')[0].strip(), 
                                       '%a, %d %b %Y %H:%M:%S %z')
            return date_obj.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
        except:
            return date_str

    def process_emails(self, service, max_results: int = 500) -> List[Dict]:
        """Main function to process emails in batches."""
        try:
            # Initialize
            self.processed_ids = self._get_processed_ids()
            self.status_text.text("📥 Fetching emails from Gmail...")
            
            # Get emails
            results = service.users().messages().list(userId='me', maxResults=max_results).execute()
            messages = results.get('messages', [])
            
            if not messages:
                self.status_text.info("No messages found in the inbox.")
                return []

            # Filter delivery emails
            delivery_emails = self._filter_delivery_emails(service, messages)
            
            if not delivery_emails:
                return []

            # Process in batches
            return self._process_batches(delivery_emails)

        except Exception as e:
            st.error(f"Error in email processing: {str(e)}")
            return []

    def _filter_delivery_emails(self, service, messages: List[Dict]) -> List[Dict]:
        """Filter and collect new delivery-related emails."""
        delivery_emails = []
        total_messages = len(messages)

        self.status_text.text(f"🔍 Scanning {total_messages} emails...")
        
        for idx, message in enumerate(messages):
            try:
                if message['id'] in self.processed_ids:
                    continue
                    
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                headers = msg['payload']['headers']
                
                # Extract email details
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')
                snippet = msg.get('snippet', '')

                # Check if delivery-related
                if self._is_delivery_related(subject, snippet):
                    delivery_emails.append({
                        'id': message['id'],
                        'subject': subject,
                        'sender': sender,
                        'date': date,
                        'body': self._extract_email_body(msg),
                        'snippet': snippet
                    })
                    self.status_text.text(f"📦 Found delivery email: {subject}")

            except Exception as e:
                st.warning(f"Error filtering email {message['id']}: {str(e)}")
                continue

            self.progress_bar.progress(min((idx + 1) / total_messages, 1.0))

        self.status_text.text(f"✅ Found {len(delivery_emails)} new delivery emails")
        return delivery_emails

    def _process_batches(self, delivery_emails: List[Dict]) -> List[Dict]:
        """Process filtered emails in batches."""
        processed_results = []
        total_batches = (len(delivery_emails) + BATCH_SIZE - 1) // BATCH_SIZE

        for i in range(0, len(delivery_emails), BATCH_SIZE):
            batch = delivery_emails[i:i + BATCH_SIZE]
            current_batch = i // BATCH_SIZE + 1
            
            self.status_text.text(f"Processing batch {current_batch} of {total_batches}")
            self.progress_bar.progress(current_batch / total_batches)
            
            results = self._process_email_batch(batch)
            processed_results.extend(results)

        self.status_text.text(f"✅ Processed {len(processed_results)} emails")
        self.progress_bar.progress(1.0)
        return processed_results

class AzureOpenAIChat:
    def __init__(self):
        self.API_ENDPOINT = st.secrets.get("AZURE_OPENAI_API_ENDPOINT", "")
        self.API_KEY = st.secrets.get("AZURE_OPENAI_API_KEY", "")

    def extract_delivery_details(self, email_body: str, max_tokens: int = 300) -> Optional[Dict]:
        """Extract structured delivery details using Azure OpenAI."""
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    self.API_ENDPOINT,
                    headers={
                        "Content-Type": "application/json",
                        "api-key": self.API_KEY,
                    },
                    json={
                        "messages": [{
                            "role": "user",
                            "content": self._create_prompt(email_body)
                        }],
                        "max_tokens": max_tokens,
                        "temperature": 0.5,
                        "top_p": 1,
                        "frequency_penalty": 0,
                        "presence_penalty": 0,
                    }
                )
                response.raise_for_status()
                sleep(RATE_LIMIT_DELAY)
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    st.error(f"API error after {MAX_RETRIES} attempts: {str(e)}")
                    return None
                sleep(2 ** attempt)
        return None

    def _create_prompt(self, email_body: str) -> str:
        """Create the prompt for delivery details extraction."""
        return f"""
        Extract delivery-related details from the following email body and return a JSON output with these keys:
        - delivery: "yes" if delivery is confirmed, otherwise "no"
        - price_num: Extracted price amount, default to 0.00 if not found
        - description: Short description of the product if available
        - order_id: Extracted order ID if available
        - delivery_date: Extracted delivery date in YYYY-MM-DD format if available
        - store: Store or sender name
        - tracking_number: Extracted tracking number if available
        - carrier: Extracted carrier name (FedEx, UPS, USPS, etc.) if available

        Email Body:
        {email_body}

        Output JSON:
        """

def get_email_messages(service, max_results: int = 500) -> List[Dict]:
    """Entry point for email processing."""
    processor = EmailProcessor()
    return processor.process_emails(service, max_results)