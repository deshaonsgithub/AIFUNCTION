# Azure Provisioning Solution - WordPress to Microsoft 365

Automated provisioning system that handles successful purchases from WordPress/MemberPress and provisions Azure/Entra/Teams/SharePoint resources.

## Architecture

```
WordPress/MemberPress Purchase
         ↓
    Ingest Function (HTTP)
         ↓
    Service Bus Queue
         ↓
    Worker Function
         ↓
  [Entra ID] → [Teams] → [SharePoint]
         ↓
  Webhook Callback to WordPress
```

## What Gets Provisioned

When a successful purchase occurs:

1. **Entra ID Guest Invite** - User receives invitation email to join your tenant
2. **Microsoft Teams Site** - Dedicated team workspace for the user
3. **Private Teams Channel** - Secure private channel within the team
4. **SharePoint Site** - Automatically created with the Team
5. **SharePoint List** - "Member Resources" list with custom columns

## Functions

### 1. Provisioning Ingest Function (HTTP Triggered)
- **Endpoint**: `POST /api/provisioning/ingest`
- **Purpose**: Receives purchase webhooks from WordPress
- **Validates**: Email format, required fields
- **Outputs**: Formatted request to Service Bus

**Request Format**:
```json
{
  "email": "user@example.com",
  "name": "John Doe",
  "firstName": "John",
  "lastName": "Doe",
  "purchaseId": "WP-12345",
  "productSku": "PREMIUM-001",
  "organization": "My Company",
  "callbackUrl": "https://yoursite.com/wp-json/custom/v1/provisioning-callback"
}
```

**Response**:
```json
{
  "status": "accepted",
  "provisioningId": "PROV-A1B2C3D4E5F6",
  "message": "Provisioning request accepted and queued"
}
```

### 2. Provisioning Worker Function (Service Bus Triggered)
- **Purpose**: Orchestrates all provisioning steps
- **Uses**: Microsoft Graph API for all operations
- **Callback**: Sends results back to WordPress

**Callback Payload**:
```json
{
  "provisioningId": "PROV-A1B2C3D4E5F6",
  "purchaseId": "WP-12345",
  "status": "completed",
  "timestamp": "2026-01-29T12:00:00Z",
  "resources": {
    "entraInvite": {
      "success": true,
      "inviteRedeemUrl": "https://login.microsoftonline.com/..."
    },
    "teamsUrl": "https://teams.microsoft.com/l/team/...",
    "sharepointUrl": "https://yourtenant.sharepoint.com/sites/...",
    "sharepointListUrl": "https://yourtenant.sharepoint.com/sites/.../Lists/..."
  }
}
```

## Setup Instructions

### Prerequisites

1. **Azure App Registration** with Microsoft Graph API permissions:
   - `User.Invite.All` (Application)
   - `Group.ReadWrite.All` (Application)
   - `Sites.ReadWrite.All` (Application)
   - `TeamMember.ReadWrite.All` (Application)
   
2. **Azure Resources**:
   - Service Bus namespace with queue: `provisioning-queue`
   - Storage Account
   - Function App (Python 3.9+)

### Step 1: Create Azure App Registration

```bash
# Login to Azure
az login

# Create app registration
az ad app create --display-name "Provisioning Function App"

# Note the Application (client) ID and create a secret
az ad app credential reset --id <APP_ID>
```

### Step 2: Grant Microsoft Graph Permissions

1. Go to Azure Portal → App Registrations → Your App
2. Click "API Permissions"
3. Add the following Microsoft Graph **Application** permissions:
   - `User.Invite.All`
   - `Group.ReadWrite.All`
   - `Sites.ReadWrite.All`
   - `TeamMember.ReadWrite.All`
4. Click "Grant admin consent"

### Step 3: Configure Environment Variables

Edit `provisioning_local.settings.json`:

```json
{
  "AZURE_TENANT_ID": "your-tenant-id",
  "AZURE_CLIENT_ID": "your-app-client-id",
  "AZURE_CLIENT_SECRET": "your-app-secret",
  "ServiceBusConnection": "your-service-bus-connection-string"
}
```

### Step 4: Install Dependencies

```bash
pip install -r provisioning_requirements.txt
```

### Step 5: Deploy to Azure

```bash
# Create Function App
az functionapp create \
  --resource-group <YOUR_RG> \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name <YOUR_FUNCTION_APP_NAME> \
  --storage-account <YOUR_STORAGE_ACCOUNT>

# Deploy
func azure functionapp publish <YOUR_FUNCTION_APP_NAME>

# Configure app settings
az functionapp config appsettings set \
  --name <YOUR_FUNCTION_APP_NAME> \
  --resource-group <YOUR_RG> \
  --settings \
    "AZURE_TENANT_ID=<YOUR_TENANT_ID>" \
    "AZURE_CLIENT_ID=<YOUR_CLIENT_ID>" \
    "AZURE_CLIENT_SECRET=<YOUR_SECRET>" \
    "ServiceBusConnection=<YOUR_CONNECTION_STRING>"
```

## WordPress/MemberPress Integration

### Option 1: Custom Webhook Action

Add to your WordPress theme's `functions.php`:

```php
add_action('mepr-event-transaction-completed', 'send_to_azure_provisioning', 10, 1);

function send_to_azure_provisioning($event) {
    $txn = $event->get_data();
    
    $payload = array(
        'email' => $txn->user()->user_email,
        'name' => $txn->user()->display_name,
        'firstName' => $txn->user()->first_name,
        'lastName' => $txn->user()->last_name,
        'purchaseId' => $txn->trans_num,
        'productSku' => $txn->product()->post_title,
        'organization' => get_bloginfo('name'),
        'callbackUrl' => get_site_url() . '/wp-json/custom/v1/provisioning-callback'
    );
    
    $response = wp_remote_post(
        'https://your-function-app.azurewebsites.net/api/provisioning/ingest?code=YOUR_FUNCTION_KEY',
        array(
            'headers' => array('Content-Type' => 'application/json'),
            'body' => json_encode($payload),
            'timeout' => 30
        )
    );
    
    if (is_wp_error($response)) {
        error_log('Provisioning webhook failed: ' . $response->get_error_message());
    }
}
```

### Option 2: Webhook Callback Handler

Create a custom REST endpoint to receive provisioning results:

```php
add_action('rest_api_init', function() {
    register_rest_route('custom/v1', '/provisioning-callback', array(
        'methods' => 'POST',
        'callback' => 'handle_provisioning_callback',
        'permission_callback' => '__return_true' // Add proper auth in production
    ));
});

function handle_provisioning_callback($request) {
    $data = $request->get_json_params();
    
    // Store provisioning results in user meta
    $purchase_id = $data['purchaseId'];
    $user = get_user_by_purchase_id($purchase_id); // Your custom function
    
    if ($user) {
        update_user_meta($user->ID, 'provisioning_status', $data['status']);
        update_user_meta($user->ID, 'teams_url', $data['resources']['teamsUrl']);
        update_user_meta($user->ID, 'sharepoint_url', $data['resources']['sharepointUrl']);
        
        // Send email to user with their resources
        send_provisioning_success_email($user, $data);
    }
    
    return new WP_REST_Response(array('success' => true), 200);
}
```

## Testing Locally

### Test Ingest Function

```bash
# Start functions locally
func start

# Send test request
curl -X POST http://localhost:7071/api/provisioning/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "name": "Test User",
    "firstName": "Test",
    "lastName": "User",
    "purchaseId": "TEST-123",
    "productSku": "PREMIUM",
    "organization": "Test Org",
    "callbackUrl": "https://webhook.site/your-test-url"
  }'
```

### Monitor Worker Function

Check logs in Azure Portal or locally:
```bash
func start --verbose
```

## Error Handling

The worker function handles errors gracefully:

- **Entra Invite Fails**: Continues with Teams creation
- **Teams Creation Fails**: Skips SharePoint list creation
- **All Steps Fail**: Still sends callback with error details

Error response example:
```json
{
  "status": "failed",
  "error": "Failed to create Teams site: Insufficient permissions",
  "results": {
    "entraInvite": {"success": true},
    "teams": {"success": false, "error": "..."}
  }
}
```

## Security Best Practices

1. **Use Managed Identity** instead of client secrets (production)
2. **Validate webhook signatures** from WordPress
3. **Use Key Vault** for secrets
4. **Enable Function authentication**
5. **Limit Service Bus access** with SAS policies
6. **Monitor with Application Insights**

## Monitoring & Troubleshooting

### Key Metrics to Track
- Provisioning success rate
- Average provisioning time
- Failed step distribution
- Callback delivery rate

### Common Issues

**Issue**: "Insufficient privileges to complete the operation"
**Solution**: Ensure app registration has admin consent for all Graph API permissions

**Issue**: "Team creation returns 404"
**Solution**: Wait 5-10 seconds after team creation before accessing it

**Issue**: "Guest invite fails"
**Solution**: Check if external user invitations are enabled in Entra ID settings

**Issue**: "Callback not received in WordPress"
**Solution**: Check WordPress site is accessible from Azure (not localhost)

## Extending the Solution

### Add Office 365 License Assignment

```python
def assign_license(token: str, user_id: str, sku_id: str):
    url = f"{GRAPH_API_BASE}/users/{user_id}/assignLicense"
    payload = {
        "addLicenses": [{"skuId": sku_id}],
        "removeLicenses": []
    }
    response = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
    return response.json()
```

### Add Power BI Workspace

```python
def create_powerbi_workspace(token: str, workspace_name: str):
    url = "https://api.powerbi.com/v1.0/myorg/groups"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"name": workspace_name}
    response = requests.post(url, headers=headers, json=payload)
    return response.json()
```

### Add SQL Database User

Connect to SQL Database and create user:
```python
import pyodbc

def create_sql_user(email: str):
    conn = pyodbc.connect(os.getenv('SQL_CONNECTION_STRING'))
    cursor = conn.cursor()
    cursor.execute(f"CREATE USER [{email}] FROM EXTERNAL PROVIDER")
    cursor.execute(f"ALTER ROLE db_datareader ADD MEMBER [{email}]")
    conn.commit()
```

## Cost Optimization

- Service Bus queue provides buffering during high load
- Async provisioning prevents timeout issues
- Failed provisions can be retried automatically
- Blob storage logs help with auditing



