/* Models module to interact with Azure OpenAI models 
This module contains functions to call different OpenAI models and return structured responses */


const OpenAI = require("openai");

const client = new OpenAI({
    apiKey: process.env.AZURE_OPENAI_KEY,
    basePath: process.env.AZURE_OPENAI_ENDPOINT
});

async function callGPT4(userMessage, contextData) {
    const completion = await client.chat.completions.create({
        model: "gpt-4o",
        messages: [
            { role: "system", content: "You are a helpful assistant." },
            { role: "system", content: contextData.context },
            { role: "user", content: userMessage }
        ]
    });

    return {
        model: "gpt-4o",
        text: completion.choices[0].message.content,
        confidence_hint: 0.9
    };
}

async function callGPT35(userMessage, contextData) {
    const completion = await client.chat.completions.create({
        model: "gpt-35-turbo",
        messages: [
            { role: "system", content: contextData.context },
            { role: "user", content: userMessage }
        ]
    });

    return {
        model: "gpt-35-turbo",
        text: completion.choices[0].message.content,
        confidence_hint: 0.7
    };
}

module.exports = { callGPT4, callGPT35 };