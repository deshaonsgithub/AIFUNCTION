/* Orchestrator module to manage RAG, model calls, and confidence scoring 
this orchestrator manages the flow of data between RAG, model calls, and confidence scoring */


const rag = require('./rag');
const models = require('./models');
const confidence = require('./confidence');

async function runOrchestration(userMessage, userId) {
    // 1. Retrieve RAG context
    const contextData = await rag.retrieveContext(userMessage);

    // 2. Call multiple models
    const responseA = await models.callGPT4(userMessage, contextData);
    const responseB = await models.callGPT35(userMessage, contextData);

    const responses = [responseA, responseB];

    // 3. Aggregate responses (simple: take GPT-4 answer)
    const finalAnswer = responseA.text;

    // 4. Compute confidence
    const confidenceScore = confidence.computeConfidence(responses);

    return {
        answer: finalAnswer,
        confidence: confidenceScore,
        sources: contextData.sources
    };
}

module.exports = { runOrchestration };