# Email Delivery Extractor

## About the Project
The **Email Delivery Extractor** is a Streamlit web application that enables users to efficiently manage their delivery-related communications by connecting securely to their Gmail account using OAuth2. It automatically identifies and aggregates emails concerning package deliveries, providing a streamlined overview directly within the app interface.

---

## Features

- **Secure Gmail Access:** Utilizes Google OAuth2 for safe and reliable user authentication.
- **Automated Email Filtering:** Scans and filters out delivery-related emails using specific search criteria.
- **User-Friendly Interface:** Displays relevant email details such as sender, subject, and content in an easily accessible format.

---

## How It Works

### User Login
- Users log in via Google OAuth2 to securely authenticate and authorize the app to access their Gmail.

### Email Filtering
- The app scans the user's inbox, applying filters to specifically retrieve emails tagged with delivery-related keywords and metadata.

### Display of Delivery Emails
- Extracted emails are presented in a clean and organized format, highlighting essential details for quick reference.

---

## Technical Setup

### OAuth2 Configuration

#### Step 1: Enable Gmail API
1. Access the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project and navigate to **APIs & Services → Library**.
3. Search and enable the **Gmail API**.

#### Step 2: Configure OAuth Consent Screen
1. Navigate to **APIs & Services → OAuth consent screen**.
2. Set user type to **External** for applications intended for public use.
3. Provide the application details and required scopes (e.g., `https://www.googleapis.com/auth/gmail.readonly`).
4. Save and submit the consent screen for verification.

#### Step 3: Generate OAuth2 Credentials
1. Proceed to **APIs & Services → Credentials**.
2. Click **Create Credentials** and select **OAuth client ID**.
3. Select application type as **Web application** and set the authorized redirect URIs.
4. Download the `client_secret.json` and save it securely in your project directory.

---

## Installation and Usage

### Prerequisites
- Python
- Pip
- Streamlit

### Installation
Install the necessary Python packages:
```bash
pip install streamlit google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### Running the Application
Execute the Streamlit application:
```bash
streamlit run app.py
```

### Using the App
1. **Sign In:** Authenticate via the Google sign-in page.
2. **View Emails:** Browse through the filtered list of delivery-related emails.
3. **Logout:** Securely logout, ensuring no sensitive data is retained.

---

## Security Measures
- Ensure the `client_secret.json` file is not included in public repositories.
- Handle OAuth tokens with care, utilizing them only during active user sessions and ensuring they are not persisted insecurely.

---

## Expected Output
- **Delivery Emails:** A list of delivery-related emails neatly displayed.
- **Secure User Authentication:** A robust login mechanism leveraging Google’s advanced security protocols.

---
This README provides a detailed overview of setting up and using the **Email Delivery Extractor** app, emphasizing security and user experience.