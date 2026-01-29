const { app } = require('@azure/functions');
const { OpenAIClient, AzureKeyCredential } = require('@azure/openai');
const axios = require('axios');

/**
 * Worker Function - Orchestrates all processing
 * - Calls RAG for context retrieval
 * - Queries multiple AI models
 * - Calculates confidence scores
 * - Stores results and sends response
 */
app.serviceBusQueue('chat-worker', {
    queueName: 'chat-processing-queue',
    connection: 'ServiceBusConnection',
    extraOutputs: [
        {
            type: 'blob',
            name: 'outputBlob',
            path: 'chat-logs/{messageId}.json',
            connection: 'AzureWebJobsStorage'
        }
    ],
    handler: async (message, context) => {
        context.log('Worker function triggered');

        try {
            // Parse message from Service Bus
            const messageBody = JSON.parse(message);
            const userMessage = messageBody.userMessage;
            const conversationId = messageBody.conversationId;
            
            context.log(`Processing message: ${messageBody.messageId}`);
            
            // Step 1: RAG Retrieval (SharePoint/Vector DB)
            const ragContext = await retrieveRagContext(userMessage, context);
            
            // Step 2: Query multiple models with confidence scoring
            const modelResponses = await queryMultipleModels(userMessage, ragContext, context);
            
            // Step 3: Select best response based on confidence
            const bestResponse = selectBestResponse(modelResponses);
            
            // Step 4: Prepare final response
            const finalResponse = {
                messageId: messageBody.messageId,
                conversationId: conversationId,
                response: bestResponse.response,
                confidenceScore: bestResponse.confidence,
                selectedModel: bestResponse.model,
                allModelScores: modelResponses.map(r => ({
                    model: r.model,
                    confidence: r.confidence
                })),
                ragSources: ragContext.sources || [],
                timestamp: messageBody.timestamp
            };
            
            // Step 5: Store to database (Cosmos DB)
            await storeToDatabase(finalResponse, context);
            
            // Step 6: Send response back (via webhook/notification)
            await sendResponseToBot(finalResponse, context);
            
            // Step 7: Save to blob storage for analytics
            context.extraOutputs.set('outputBlob', JSON.stringify(finalResponse, null, 2));
            
            context.log(`Successfully processed message with ${bestResponse.confidence.toFixed(2)} confidence`);
            
        } catch (error) {
            context.log.error('Error in worker function:', error);
            throw error;
        }
    }
});

/**
 * Retrieve relevant context from SharePoint/Vector Database
 */
async function retrieveRagContext(query, context) {
    try {
        const searchEndpoint = process.env.VECTOR_SEARCH_ENDPOINT;
        const searchKey = process.env.VECTOR_SEARCH_KEY;
        
        // Simplified RAG call - expand based on your setup
        const payload = {
            search: query,
            top: 3,
            vectorQueries: [{
                kind: 'text',
                text: query,
                k: 3,
                fields: 'contentVector'
            }]
        };
        
        // Mock response for starter - replace with actual API call
        // const response = await axios.post(
        //     `${searchEndpoint}/indexes/knowledge-base/docs/search`,
        //     payload,
        //     {
        //         headers: {
        //             'Content-Type': 'application/json',
        //             'api-key': searchKey
        //         }
        //     }
        // );
        
        // For now, return mock context
        const ragContext = {
            context: 'Retrieved relevant information from knowledge base...',
            sources: ['SharePoint Doc 1', 'SharePoint Doc 2'],
            relevanceScore: 0.85
        };
        
        context.log(`RAG retrieval completed with ${ragContext.sources.length} sources`);
        return ragContext;
        
    } catch (error) {
        context.log.warn('RAG retrieval failed:', error.message);
        return { context: '', sources: [], relevanceScore: 0.0 };
    }
}

/**
 * Query multiple AI models and calculate confidence scores
 */
async function queryMultipleModels(userMessage, ragContext, context) {
    const endpoint = process.env.AZURE_OPENAI_ENDPOINT;
    const apiKey = process.env.AZURE_OPENAI_KEY;
    
    const client = new OpenAIClient(endpoint, new AzureKeyCredential(apiKey));
    
    const modelsToQuery = [
        { name: 'gpt-4', deployment: 'gpt-4' },
        { name: 'gpt-35-turbo', deployment: 'gpt-35-turbo' }
    ];
    
    const responses = [];
    
    for (const model of modelsToQuery) {
        try {
            // Construct prompt with RAG context
            const systemPrompt = `You are a helpful assistant. 
Use the following context to answer the user's question:

Context: ${ragContext.context || ''}

Provide a confidence score (0-1) for your answer.`;
            
            const messages = [
                { role: 'system', content: systemPrompt },
                { role: 'user', content: userMessage }
            ];
            
            const result = await client.getChatCompletions(
                model.deployment,
                messages,
                {
                    temperature: 0.7,
                    maxTokens: 500
                }
            );
            
            const answer = result.choices[0].message.content;
            const finishReason = result.choices[0].finishReason;
            
            // Calculate confidence score
            const confidence = calculateConfidenceScore(
                answer,
                ragContext.relevanceScore || 0.5,
                finishReason
            );
            
            responses.push({
                model: model.name,
                response: answer,
                confidence: confidence,
                tokensUsed: result.usage.totalTokens
            });
            
            context.log(`${model.name} responded with confidence: ${confidence.toFixed(2)}`);
            
        } catch (error) {
            context.log.error(`Error querying ${model.name}:`, error.message);
            responses.push({
                model: model.name,
                response: 'Error generating response',
                confidence: 0.0,
                error: error.message
            });
        }
    }
    
    return responses;
}

/**
 * Calculate confidence score based on multiple factors
 */
function calculateConfidenceScore(response, ragScore, finishReason) {
    let baseConfidence = 0.7;
    
    // Adjust for RAG relevance
    let confidence = baseConfidence * (0.7 + 0.3 * ragScore);
    
    // Adjust for completion quality
    if (finishReason === 'stop') {
        confidence *= 1.0;
    } else if (finishReason === 'length') {
        confidence *= 0.8;
    } else {
        confidence *= 0.6;
    }
    
    // Adjust for response length (simple heuristic)
    const wordCount = response.split(/\s+/).length;
    if (wordCount >= 20 && wordCount <= 200) {
        confidence *= 1.0;
    } else if (wordCount < 20) {
        confidence *= 0.8;
    } else {
        confidence *= 0.9;
    }
    
    return Math.min(confidence, 1.0);
}

/**
 * Select the best response based on confidence scores
 */
function selectBestResponse(modelResponses) {
    // Sort by confidence score (descending)
    const sorted = [...modelResponses].sort((a, b) => b.confidence - a.confidence);
    return sorted[0];
}

/**
 * Store response to Cosmos DB for tracking and analytics
 */
async function storeToDatabase(responseData, context) {
    try {
        // TODO: Implement actual Cosmos DB insertion
        // const { CosmosClient } = require('@azure/cosmos');
        // const client = new CosmosClient({
        //     endpoint: process.env.COSMOS_DB_ENDPOINT,
        //     key: process.env.COSMOS_DB_KEY
        // });
        // const database = client.database('ChatDatabase');
        // const container = database.container('Conversations');
        // await container.items.create(responseData);
        
        context.log(`Storing to database: ${responseData.messageId}`);
        
    } catch (error) {
        context.log.error('Database storage failed:', error.message);
    }
}

/**
 * Send response back to Azure Bot Service via webhook
 */
async function sendResponseToBot(responseData, context) {
    try {
        const webhookUrl = process.env.BOT_WEBHOOK_URL;
        
        if (!webhookUrl) {
            context.log.warn('No webhook URL configured');
            return;
        }
        
        const payload = {
            conversationId: responseData.conversationId,
            text: responseData.response,
            metadata: {
                confidence: responseData.confidenceScore,
                model: responseData.selectedModel
            }
        };
        
        // TODO: Implement actual webhook call
        // await axios.post(webhookUrl, payload);
        
        context.log(`Response sent to bot for conversation: ${responseData.conversationId}`);
        
    } catch (error) {
        context.log.error('Failed to send response to bot:', error.message);
    }
}
