import logging
import json
import azure.functions as func
from datetime import datetime, timezone
import hashlib

def main(req: func.HttpRequest, msg: func.Out[str]) -> func.HttpResponse:
    """
    Provisioning Ingest Function - Handles successful purchase webhooks
    Triggered by HTTP POST from WordPress/MemberPress
    Validates and formats provisioning request, outputs to Service Bus
    """
    logging.info('Provisioning ingest function triggered')
    
    try:
        # Parse incoming webhook from WordPress/MemberPress
        req_body = req.get_json()
        
        # Extract purchase/user information
        user_email = req_body.get('email', '').strip().lower()
        user_name = req_body.get('name', '')
        first_name = req_body.get('firstName', '')
        last_name = req_body.get('lastName', '')
        purchase_id = req_body.get('purchaseId', '')
        product_sku = req_body.get('productSku', '')
        organization = req_body.get('organization', 'Default Org')
        
        # Validate required fields
        if not user_email or not user_name:
            logging.error('Missing required fields: email or name')
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields: email and name"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate email format
        if '@' not in user_email or '.' not in user_email:
            logging.error(f'Invalid email format: {user_email}')
            return func.HttpResponse(
                json.dumps({"error": "Invalid email format"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Generate unique provisioning ID
        provisioning_id = generate_provisioning_id(user_email, purchase_id)
        
        # Format provisioning request
        provisioning_request = {
            "provisioningId": provisioning_id,
            "purchaseId": purchase_id,
            "timestamp": datetime.utcnow().isoformat(),
            "user": {
                "email": user_email,
                "displayName": user_name,
                "firstName": first_name,
                "lastName": last_name
            },
            "organization": organization,
            "productSku": product_sku,
            "provisioning": {
                "entraInvite": True,
                "teamsChannel": True,
                "sharepointSite": True,
                "sharepointList": True
            },
            "status": "pending",
            "webhookUrl": req_body.get('callbackUrl', '')
        }
        
        # Send to Service Bus Queue for worker processing
        msg.set(json.dumps(provisioning_request))
        
        logging.info(f'Provisioning request queued: {provisioning_id} for {user_email}')
        
        # Return immediate acknowledgment
        return func.HttpResponse(
            json.dumps({
                "status": "accepted",
                "provisioningId": provisioning_id,
                "message": "Provisioning request accepted and queued"
            }),
            status_code=202,
            mimetype="application/json"
        )
        
    except ValueError as e:
        logging.error(f'Invalid JSON in request: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON format"}),
            status_code=400,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.error(f'Error in provisioning ingest: {str(e)}', exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json"
        )


def generate_provisioning_id(email: str, purchase_id: str) -> str:
    """Generate a unique provisioning ID"""
    timestamp = datetime.now(timezone.utc).isoformat()
    hash_input = f"{email}_{purchase_id}_{timestamp}"
    hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:12]
    return f"PROV-{hash_value.upper()}"
