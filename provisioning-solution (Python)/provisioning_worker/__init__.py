import logging
import json
import os
import asyncio
from typing import Dict, Any, List
import azure.functions as func
import requests
from msal import ConfidentialClientApplication
from datetime import datetime, timezone

# Microsoft Graph API endpoints
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_API_BETA = "https://graph.microsoft.com/beta"


def main(msg: func.ServiceBusMessage, outputBlob: func.Out[str]) -> None:
    """
    Provisioning Worker Function - Orchestrates Azure/Entra/Teams provisioning
    Steps:
    1. Send Entra ID guest invite
    2. Create Teams site with private channel
    3. Create SharePoint site and list
    4. Send provisioning results back to WordPress via REST POST
    """
    logging.info('Provisioning worker function triggered')
    
    try:
        # Parse provisioning request from Service Bus
        request_body = json.loads(msg.get_body().decode('utf-8'))
        provisioning_id = request_body['provisioningId']
        user_info = request_body['user']
        
        logging.info(f'Processing provisioning: {provisioning_id} for {user_info["email"]}')
        
        # Get Microsoft Graph access token
        access_token = get_graph_access_token()
        
        # Initialize results tracker
        provisioning_results = {
            "provisioningId": provisioning_id,
            "purchaseId": request_body['purchaseId'],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
            "results": {}
        }
        
        try:
            # Step 1: Send Entra ID guest invite
            logging.info(f'Step 1: Sending Entra ID invite to {user_info["email"]}')
            invite_result = send_entra_guest_invite(access_token, user_info)
            provisioning_results['results']['entraInvite'] = invite_result
            
            # Step 2: Create Teams site with private channel
            logging.info('Step 2: Creating Teams site and private channel')
            teams_result = create_teams_site_with_channel(
                access_token, 
                user_info,
                request_body['organization']
            )
            provisioning_results['results']['teams'] = teams_result
            
            # Step 3: Create SharePoint site and list
            logging.info('Step 3: Creating SharePoint site and list')
            sharepoint_result = create_sharepoint_site_and_list(
                access_token,
                teams_result.get('teamId'),
                user_info,
                request_body['organization']
            )
            provisioning_results['results']['sharepoint'] = sharepoint_result
            
            # Mark as successful
            provisioning_results['status'] = 'completed'
            provisioning_results['message'] = 'All resources provisioned successfully'
            
            logging.info(f'Provisioning completed successfully: {provisioning_id}')
            
        except Exception as provision_error:
            # Mark as failed but continue to send notification
            logging.error(f'Provisioning error: {str(provision_error)}', exc_info=True)
            provisioning_results['status'] = 'failed'
            provisioning_results['error'] = str(provision_error)
        
        # Step 4: Send results back to WordPress via REST POST
        webhook_url = request_body.get('webhookUrl')
        if webhook_url:
            logging.info(f'Step 4: Sending results to webhook: {webhook_url}')
            send_provisioning_callback(webhook_url, provisioning_results)
        else:
            logging.warning('No webhook URL provided, skipping callback')
        
        # Save results to blob storage
        outputBlob.set(json.dumps(provisioning_results, indent=2))
        
        logging.info(f'Provisioning workflow completed: {provisioning_id}')
        
    except Exception as e:
        logging.error(f'Critical error in provisioning worker: {str(e)}', exc_info=True)
        raise


def get_graph_access_token() -> str:
    """
    Get Microsoft Graph API access token using MSAL
    """
    tenant_id = os.getenv('AZURE_TENANT_ID')
    client_id = os.getenv('AZURE_CLIENT_ID')
    client_secret = os.getenv('AZURE_CLIENT_SECRET')
    
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scope = ["https://graph.microsoft.com/.default"]
    
    app = ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret
    )
    
    result = app.acquire_token_for_client(scopes=scope)
    
    if "access_token" in result:
        logging.info('Successfully acquired Graph API access token')
        return result["access_token"]
    else:
        error_msg = result.get("error_description", "Unknown error")
        logging.error(f'Failed to acquire token: {error_msg}')
        raise Exception(f"Failed to get access token: {error_msg}")


def send_entra_guest_invite(token: str, user_info: Dict[str, str]) -> Dict[str, Any]:
    """
    Send guest invitation to Entra ID (Azure AD)
    """
    try:
        url = f"{GRAPH_API_BASE}/invitations"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Prepare invitation payload
        payload = {
            "invitedUserEmailAddress": user_info['email'],
            "invitedUserDisplayName": user_info['displayName'],
            "inviteRedirectUrl": os.getenv('INVITE_REDIRECT_URL', 'https://myapps.microsoft.com'),
            "sendInvitationMessage": True,
            "invitedUserMessageInfo": {
                "customizedMessageBody": f"Welcome {user_info['displayName']}! You've been invited to access our platform."
            }
        }
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        logging.info(f'Guest invite sent successfully: {result.get("id")}')
        
        return {
            "success": True,
            "inviteId": result.get('id'),
            "inviteRedeemUrl": result.get('inviteRedeemUrl'),
            "invitedUserEmailAddress": result.get('invitedUserEmailAddress'),
            "status": result.get('status')
        }
        
    except requests.exceptions.RequestException as e:
        logging.error(f'Entra invite failed: {str(e)}')
        return {
            "success": False,
            "error": str(e)
        }


def create_teams_site_with_channel(token: str, user_info: Dict[str, str], organization: str) -> Dict[str, Any]:
    """
    Create a Microsoft Teams site with a private channel
    """
    try:
        # Step 1: Create the Team
        url = f"{GRAPH_API_BASE}/teams"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        team_name = f"{organization} - {user_info['displayName']}"
        
        team_payload = {
            "template@odata.bind": "https://graph.microsoft.com/v1.0/teamsTemplates('standard')",
            "displayName": team_name,
            "description": f"Team workspace for {user_info['displayName']}",
            "members": [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_info['email']}')"
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=team_payload)
        response.raise_for_status()
        
        # Get team ID from location header
        team_location = response.headers.get('Content-Location', '')
        team_id = team_location.split("'")[1] if "'" in team_location else None
        
        if not team_id:
            raise Exception("Failed to extract team ID from response")
        
        logging.info(f'Team created successfully: {team_id}')
        
        # Step 2: Wait for team provisioning to complete (Teams creation is async)
        import time
        time.sleep(5)  # Give Teams time to provision
        
        # Step 3: Create private channel
        channel_url = f"{GRAPH_API_BASE}/teams/{team_id}/channels"
        channel_payload = {
            "displayName": "Private Workspace",
            "description": "Private channel for confidential discussions",
            "membershipType": "private",
            "members": [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_info['email']}')"
                }
            ]
        }
        
        channel_response = requests.post(channel_url, headers=headers, json=channel_payload)
        channel_response.raise_for_status()
        
        channel_result = channel_response.json()
        channel_id = channel_result.get('id')
        
        logging.info(f'Private channel created: {channel_id}')
        
        return {
            "success": True,
            "teamId": team_id,
            "teamName": team_name,
            "channelId": channel_id,
            "channelName": channel_result.get('displayName'),
            "webUrl": f"https://teams.microsoft.com/l/team/{team_id}"
        }
        
    except requests.exceptions.RequestException as e:
        logging.error(f'Teams creation failed: {str(e)}')
        return {
            "success": False,
            "error": str(e)
        }


def create_sharepoint_site_and_list(token: str, team_id: str, user_info: Dict[str, str], organization: str) -> Dict[str, Any]:
    """
    Create SharePoint site and list
    Note: When a Team is created, a SharePoint site is automatically created
    This function accesses that site and creates a custom list
    """
    try:
        if not team_id:
            raise Exception("Team ID required to access SharePoint site")
        
        # Step 1: Get the SharePoint site associated with the Team
        url = f"{GRAPH_API_BASE}/groups/{team_id}/sites/root"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        site_info = response.json()
        site_id = site_info.get('id')
        site_url = site_info.get('webUrl')
        
        logging.info(f'SharePoint site found: {site_url}')
        
        # Step 2: Create a custom list in the SharePoint site
        list_url = f"{GRAPH_API_BASE}/sites/{site_id}/lists"
        
        list_payload = {
            "displayName": "Member Resources",
            "columns": [
                {
                    "name": "ResourceName",
                    "text": {}
                },
                {
                    "name": "ResourceType",
                    "choice": {
                        "choices": ["Document", "Link", "Video", "Other"]
                    }
                },
                {
                    "name": "Description",
                    "text": {
                        "allowMultipleLines": True
                    }
                }
            ],
            "list": {
                "template": "genericList"
            }
        }
        
        list_response = requests.post(list_url, headers=headers, json=list_payload)
        list_response.raise_for_status()
        
        list_result = list_response.json()
        list_id = list_result.get('id')
        
        logging.info(f'SharePoint list created: {list_id}')
        
        return {
            "success": True,
            "siteId": site_id,
            "siteUrl": site_url,
            "listId": list_id,
            "listName": list_result.get('displayName'),
            "listWebUrl": list_result.get('webUrl')
        }
        
    except requests.exceptions.RequestException as e:
        logging.error(f'SharePoint provisioning failed: {str(e)}')
        return {
            "success": False,
            "error": str(e)
        }


def send_provisioning_callback(webhook_url: str, provisioning_results: Dict[str, Any]) -> None:
    """
    Send provisioning results back to WordPress via REST POST
    """
    try:
        # Prepare callback payload
        callback_payload = {
            "provisioningId": provisioning_results['provisioningId'],
            "purchaseId": provisioning_results['purchaseId'],
            "status": provisioning_results['status'],
            "timestamp": provisioning_results['timestamp'],
            "resources": {
                "entraInvite": provisioning_results['results'].get('entraInvite', {}),
                "teamsUrl": provisioning_results['results'].get('teams', {}).get('webUrl'),
                "sharepointUrl": provisioning_results['results'].get('sharepoint', {}).get('siteUrl'),
                "sharepointListUrl": provisioning_results['results'].get('sharepoint', {}).get('listWebUrl')
            }
        }
        
        # Add error info if failed
        if provisioning_results['status'] == 'failed':
            callback_payload['error'] = provisioning_results.get('error')
        
        # Send POST request to WordPress webhook
        headers = {
            "Content-Type": "application/json",
            "X-Provisioning-ID": provisioning_results['provisioningId']
        }
        
        response = requests.post(
            webhook_url,
            json=callback_payload,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        
        logging.info(f'Callback sent successfully to {webhook_url}')
        
    except requests.exceptions.RequestException as e:
        logging.error(f'Failed to send callback: {str(e)}')
        # Don't raise exception - we don't want to fail the entire provisioning
