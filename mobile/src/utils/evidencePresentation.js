// Present an existing, validated inference without regenerating its verdict or
// rewriting the saved quotation. Older/other result contracts keep their text.
export function evidencePresentation(result) {
  const inference = result.inference_context;
  const source = (result.evidence || []).find(item => item.evidence_id === inference?.evidence_id);
  if (result.assessment_outcome === 'likely_misinformation'
      && result.scoring?.status === 'inference_based'
      && typeof inference?.baseline_quote === 'string' && inference.baseline_quote.trim() && source) {
    return {
      explanation: 'The current official information weighs against this claim. Our searches of the listed official sources found no supporting announcement. This is a limited assessment; new information could change the result.',
      quote: inference.baseline_quote,
      source,
    };
  }
  return { explanation: result.explanation || '', quote: null, source: null };
}
