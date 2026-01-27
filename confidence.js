/* Confidence module to compute confidence scores 
This module computes confidence scores based on model responses */

function computeConfidence(responses) {
    const scores = responses.map(r => r.confidence_hint);
    const average = scores.reduce((a, b) => a + b, 0) / scores.length;
    return Math.round(average * 100) / 100;
}

module.exports = { computeConfidence };