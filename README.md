Join the Community
[Join Curious PM Community](https://curious.pm) to connect, share, and learn with others!

This Streamlit app enables users to authenticate with Google OAuth, access their Gmail, and view emails and images directly in a web interface.

### Configuration and Setup
- **Page Settings**: Configures the Streamlit page with a title and layout.
- **Google API Scope**: Specifies the permissions the app needs to access the user's Gmail account, specifically, read-only access to the user's emails.
- **Session State Variables**: Streamlit uses session states to keep track of user-specific information across interactions. In this case, it tracks the logged-in user's email, page token for pagination, and credentials.

### Authentication Function (`authenticate_user`)
- This function handles user authentication using Google's OAuth2 flow.
- It first checks if there are existing credentials that are still valid. If not, it proceeds to authenticate the user.
- If the credentials are expired, it attempts to refresh them.
- If no credentials are available or they can't be refreshed, it initializes an OAuth flow using client configuration details stored in Streamlit secrets. This includes client ID, client secret, and redirect URIs.
- The function generates an authorization URL that the user needs to visit to grant the app access to their Gmail account. The user will be guided to authenticate via a link presented in the app.
- Once authenticated, credentials are stored in the session state for subsequent use.

### Email Handling Functions
- **`decode_email_body`**: Parses the body of the email and extracts content and inline images, handling different content types (like text and images) found in the email parts.
- **`fetch_emails`**: Connects to the Gmail API to fetch a list of emails. It handles pagination through a page token and gathers basic details about each email, such as the sender, subject, and body. It uses the previously defined `decode_email_body` function to parse each email.

### User Interface
- **Main App Layout**: Introduces the app and prompts the user to connect to their Gmail.
- **Sign-in Handling**: Includes a button that triggers the authentication process. If the user is already logged in, it displays their email address and a logout button.
- **Email Display**: If the user is authenticated, the app calls `fetch_emails` to load emails and displays them using expanders (collapsible sections) for each email. Each expander shows the sender, subject, and formatted email body. If any inline images are present, they are also displayed.
- **Pagination**: Allows the user to navigate through their emails page by page, with buttons to go to the previous or next page of emails.

Creating a `secrets.json` file for use with Google Cloud APIs typically involves creating credentials in the Google Cloud Console. Here's a detailed step-by-step guide to obtaining the necessary credentials and formatting them into a `secrets.json` file:

### Step 1: Create a Google Cloud Project
1. **Go to the Google Cloud Console**: Open your web browser and go to the [Google Cloud Console](https://console.cloud.google.com/).
2. **Sign In**: Log in with your Google account.
3. **Create a New Project**: Click on the project dropdown (top navigation bar) and then click "New Project". Enter your project details (name and location) and click "Create".

### Step 2: Enable Gmail API
1. **API Library**: From your project's dashboard, navigate to "APIs & Services" > "Library".
2. **Search for Gmail API**: In the search box, type "Gmail" and select "Gmail API".
3. **Enable API**: Click the "Enable" button to activate the Gmail API for your project.

### Step 3: Create Credentials
1. **Credentials Dashboard**: Navigate to "APIs & Services" > "Credentials".
2. **Create Credentials**: Click on "Create Credentials" at the top of the page and select "OAuth client ID".
3. **Configure Consent Screen**:
   - You may be prompted to configure the "OAuth consent screen" first. Click on the “Configure consent screen” and select the user type (usually "External" for apps used by people outside your organization).
   - Fill in the required fields: app name, user support email, and developer contact information. Save and continue.
   - Add the scopes you need for the Gmail API, such as `https://www.googleapis.com/auth/gmail.readonly`. Save and continue.
   - Add test users (your Google account email), and then save and continue.
4. **Create OAuth Client ID**:
   - **Application Type**: Choose "Web application".
   - **Name**: Give a name to your OAuth 2.0 client.
   - **Authorized redirect URIs**: Add the URI(s) where your application will receive the OAuth2 response, e.g., `http://localhost:3000/oauth2callback` (for local testing).
   - Click "Create".

### Step 4: Download Credentials
1. **Download JSON**: After creating the OAuth client ID, click on the download icon (Download JSON) next to the client ID you just created. This downloads the `credentials.json` file.

### Step 5: Format as `secrets.json`
1. **Rename and Edit**: Rename the downloaded file to `secrets.json`. This file will look something like this:
   ```json
   {
       "installed": {
           "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
           "project_id": "YOUR_PROJECT_ID",
           "auth_uri": "https://accounts.google.com/o/oauth2/auth",
           "token_uri": "https://oauth2.googleapis.com/token",
           "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
           "client_secret": "YOUR_CLIENT_SECRET",
           "redirect_uris": ["YOUR_REDIRECT_URI"]
       }
   }
   ```

### Step 6: Use `secrets.json` in Your Application
- Use this `secrets.json` in your application to configure the OAuth2 client setup. This file contains sensitive information (like your client secret), so keep it secure and do not expose it publicly.

