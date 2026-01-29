# Azure Chat Bot Monitoring Solution (Node.js)

Simple Node.js-based solution with two Azure Functions for orchestrating chat bot messages with multi-model confidence scoring and RAG integration.

## Architecture Overview

```
Bot Service → Ingest Function → Service Bus Queue → Worker Function → Response
                                                    ↓
                                          [RAG + Multi-Model + DB]
```

## Functions

### 1. Ingest Function (HTTP Triggered)
- **Purpose**: Intake and format incoming chat messages
- **Trigger**: HTTP POST from Azure Bot Service
- **Output**: Message to Service Bus Queue
- **Endpoint**: `POST /api/chat/ingest`
- **Runtime**: Node.js 18+

**Request Format**:
```json
{
  "message": "User's question here",
  "userId": "user123",
  "conversationId": "conv456"
}
```

**Response**:
```json
{
  "status": "accepted",
  "messageId": "conv456_1706534400000"
}
```

### 2. Worker Function (Service Bus Triggered)
- **Purpose**: Orchestrates all processing
  - Retrieves RAG context from SharePoint/Vector DB
  - Queries multiple AI models (GPT-4, GPT-3.5)
  - Calculates confidence scores
  - Selects best response
  - Stores to Cosmos DB
  - Sends response back to bot

## Setup Instructions

### Prerequisites
- Node.js 18+ installed
- Azure subscription
- Azure Functions Core Tools
- Azure OpenAI resource
- Service Bus namespace
- Cosmos DB account (optional)
- Azure Cognitive Search (for RAG, optional)

### 1. Install Dependencies

```bash
cd nodejs-chat-monitoring
npm install
```

### 2. Configure Environment Variables

Edit `local.settings.json` and add your Azure resource credentials:

```json
{
  "Values": {
    "ServiceBusConnection": "Endpoint=sb://...",
    "AZURE_OPENAI_KEY": "your-key-here",
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "VECTOR_SEARCH_ENDPOINT": "https://your-search.search.windows.net",
    "VECTOR_SEARCH_KEY": "your-search-key",
    "COSMOS_DB_ENDPOINT": "https://your-cosmos.documents.azure.com:443/",
    "COSMOS_DB_KEY": "your-cosmos-key",
    "BOT_WEBHOOK_URL": "https://your-bot-webhook-url"
  }
}
```

### 3. Run Locally

```bash
npm start
# or
func start
```

### 4. Test the Ingest Function

```bash
curl -X POST http://localhost:7071/api/chat/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is our refund policy?",
    "userId": "test-user",
    "conversationId": "test-conv-123"
  }'
```

Expected Response:
```json
{
  "status": "accepted",
  "messageId": "test-conv-123_1706534400000"
}
```

### 5. Deploy to Azure

```bash
# Login to Azure
az login

# Create Function App
az functionapp create \
  --resource-group <YOUR_RG> \
  --consumption-plan-location eastus \
  --runtime node \
  --runtime-version 18 \
  --functions-version 4 \
  --name <YOUR_FUNCTION_APP_NAME> \
  --storage-account <YOUR_STORAGE_ACCOUNT>

# Deploy functions
func azure functionapp publish <YOUR_FUNCTION_APP_NAME>
```

### 6. Configure Application Settings in Azure

```bash
# Set environment variables
az functionapp config appsettings set \
  --name <YOUR_FUNCTION_APP_NAME> \
  --resource-group <YOUR_RG> \
  --settings \
    "AZURE_OPENAI_KEY=<YOUR_KEY>" \
    "AZURE_OPENAI_ENDPOINT=<YOUR_ENDPOINT>" \
    "ServiceBusConnection=<YOUR_CONNECTION_STRING>" \
    # ... add all other settings
```

## Project Structure

```
nodejs-chat-monitoring/
├── src/
│   └── functions/
│       ├── chatIngest.js      # HTTP triggered ingest function
│       └── chatWorker.js      # Service Bus triggered worker
├── package.json               # Dependencies
├── host.json                  # Function host configuration
├── local.settings.json        # Local environment variables
└── README.md                  # This file
```

## Confidence Scoring

The worker function calculates confidence scores based on:

1. **RAG Relevance Score** (0-1): How relevant the retrieved context is
2. **Completion Quality**: Whether the model finished naturally (`stop`) or hit limits
3. **Response Length**: Optimal length responses (20-200 words) score higher
4. **Model Performance**: Different models can be weighted differently

Formula:
```javascript
confidence = baseConfidence * (0.7 + 0.3 * ragScore) * completionFactor * lengthFactor
```

Final score is between 0-1, with higher scores indicating more confident responses.

## Multi-Model Orchestration

Currently queries two models:
- **GPT-4**: Higher quality, more capable
- **GPT-3.5-Turbo**: Faster, more cost-effective

The function selects the response with the highest confidence score.

To add more models, edit `chatWorker.js`:

```javascript
const modelsToQuery = [
    { name: 'gpt-4', deployment: 'gpt-4' },
    { name: 'gpt-35-turbo', deployment: 'gpt-35-turbo' },
    { name: 'custom-model', deployment: 'your-deployment-name' }
];
```

### View Logs

**Locally:**
```bash
func start --verbose
```

**Azure Portal:**
1. Go to your Function App
2. Click "Log stream" or "Application Insights"
3. View real-time logs and metrics

### Common Issues

**Issue**: "Module not found"
**Solution**: Run `npm install` to install dependencies

**Issue**: "Connection timeout to Service Bus"
**Solution**: Check your ServiceBusConnection string is correct

**Issue**: "Azure OpenAI rate limit exceeded"
**Solution**: Add retry logic with exponential backoff

**Issue**: "Worker function not triggering"
**Solution**: Verify Service Bus queue name matches in both functions

## Performance Optimization

1. **Parallel Model Calls**: Use `Promise.all()` to query models simultaneously
2. **Caching**: Cache common RAG results
3. **Token Limits**: Set appropriate `maxTokens` for each model
4. **Service Bus Batching**: Process multiple messages in batches



## Troubleshooting

### Debug Mode

Enable detailed logging:
```json
{
  "logging": {
    "logLevel": {
      "default": "Debug"
    }
  }
}
```

### Test Service Bus Connection

```javascript
const { ServiceBusClient } = require('@azure/service-bus');

const client = new ServiceBusClient(process.env.ServiceBusConnection);
const sender = client.createSender('chat-processing-queue');

await sender.sendMessages({
    body: JSON.stringify({ test: 'message' })
});
```