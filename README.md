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

## OAuth2 Setup Steps

### Step 1: Enable Gmail API in Google Cloud Console
1. **Go to Google Cloud Console:** [Google Cloud Console](https://console.cloud.google.com/).
2. **Create a project:**
   - Navigate to the top-left menu → Project selector → **New Project**.
3. **Enable the Gmail API:**
   - Go to **APIs & Services → Library**.
   - Search for **Gmail API** and enable it for your project.

### Step 2: Set Up OAuth Consent Screen
1. Go to **APIs & Services → OAuth consent screen**.
2. Choose **External** if you’re allowing public users.
3. Fill out basic details like the app name and user support email.
4. Ensure you add the scope for reading Gmail:

https://www.googleapis.com/auth/gmail.readonly

5. Save and publish the consent screen.

### Step 3: Create OAuth2 Credentials
1. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Choose **Desktop App** (for local testing).
3. Download the `client_secret.json` file.

### Step 4: Place `client_secret.json` in Your Project Directory
- Place it in the same directory as `app.py`.

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
