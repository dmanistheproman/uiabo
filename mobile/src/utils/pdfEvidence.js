const cell = value => String(value ?? '').replace(/\\/g, '\\\\').replace(/\|/g, '\\|').replace(/[\r\n]+/g, ' ').replace(/[<>]/g, '');

export function pdfSeriesTable(series) {
  const rows = (series.points || []).map(point => {
    const unit = { percent: '%', people: 'people', currency: '(currency as printed)', other: '' }[point.unit] || '';
    return `| ${cell(point.date_label)} | ${cell(point.value)} ${unit} | ${cell(point.cohort_label || 'Not specified')} |`;
  });
  return ['| Date | Value | Cohort |', '| --- | --- | --- |', ...rows].join('\n');
}
