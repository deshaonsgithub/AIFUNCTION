/* Azure Function entry point 
This check if the server is running*/

const orchestrator = require('./orchestrator');

module.exports = async function (context, req) {
    try {
        const { message, user_id } = req.body || {};
        if (!message) throw new Error("Missing 'message' field");

        const result = await orchestrator.runOrchestration(message, user_id || "anonymous");

        context.res = {
            status: 200,
            body: result
        };
    } catch (error) {
        context.res = {
            status: 500,
            body: { error: error.message }
        };
    }
};