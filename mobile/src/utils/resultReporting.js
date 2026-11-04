export function reportOptions(result) {
  const type = result?.input_type || 'text';
  const options = [{ value: 'wrong_label', label: type === 'link_safety' ? 'The link safety result is wrong' : 'The result label is wrong' }];
  if (!['image_context', 'link_safety'].includes(type)) {
    options.push({ value: 'wrong_score', label: type === 'deepfake_ai' ? 'The confidence score is wrong' : 'The credibility score is wrong' });
  }
  options.push({ value: 'wrong_evidence', label: type === 'deepfake_ai' ? 'The explanation is wrong' : 'The evidence or explanation is wrong' });
  options.push({ value: 'other', label: 'Something else' });
  return options;
}

export function canReport(result) {
  return !!result?.result_id && result.processing_status === 'completed';
}
