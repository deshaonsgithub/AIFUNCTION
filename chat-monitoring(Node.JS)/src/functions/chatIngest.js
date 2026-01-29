const { app } = require('@azure/functions');

/**
 * Ingest Function - Handles incoming chat messages and formats them for processing
 * Triggered by HTTP request from Azure Bot Service
 * Outputs to Service Bus Queue for worker function
 */
app.http('chat-ingest', {
    methods: ['POST'],
    authLevel: 'function',
    route: 'chat/ingest',
    extraOutputs: [
        {
            type: 'serviceBus',
            name: 'outputMessage',
            queueName: 'chat-processing-queue',
            connection: 'ServiceBusConnection'
        }
    ],
    handler: async (request, context) => {
        context.log('Ingest function processing chat message');

        try {
            // Parse incoming request
            const body = await request.json();
            
            // Extract message data
            const userMessage = body.message || '';
            const userId = body.userId || 'unknown';
            const conversationId = body.conversationId || '';
            
            // Validate input
            if (!userMessage) {
                return {
                    status: 400,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ error: 'Message is required' })
                };
            }
            
            // Format message for processing
            const formattedMessage = {
                messageId: `${conversationId}_${Date.now()}`,
                conversationId: conversationId,
                userId: userId,
                userMessage: userMessage,
                timestamp: new Date().toISOString(),
                metadata: {
                    source: 'bot_service',
                    requiresRAG: true,
                    requiresMultiModel: true
                }
            };
            
            // Send to Service Bus Queue for worker processing
            context.extraOutputs.set('outputMessage', JSON.stringify(formattedMessage));
            
            context.log(`Message queued successfully: ${formattedMessage.messageId}`);
            
            // Return immediate acknowledgment to bot
            return {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    status: 'accepted',
                    messageId: formattedMessage.messageId
                })
            };
            
        } catch (error) {
            context.log.error('Error in ingest function:', error);
            
            return {
                status: 500,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ error: 'Internal server error' })
            };
        }
    }
});
