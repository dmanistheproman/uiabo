import MarkdownIt from 'markdown-it';

// Parse to native views, never HTML or a WebView. Keep typography unchanged so
// quantities, negations and quotation marks in source evidence remain intact.
const markdown = new MarkdownIt({ html: false, linkify: false, typographer: false, breaks: true });

function tree(tokens) {
  const root = { children: [] };
  const stack = [root];
  for (const token of tokens) {
    if (token.nesting === -1) { stack.pop(); continue; }
    const node = { type: token.type.replace(/_open$/, ''), tag: token.tag,
      content: token.content, attrs: Object.fromEntries(token.attrs || []),
      children: token.children ? tree(token.children) : [] };
    stack[stack.length - 1].children.push(node);
    if (token.nesting === 1) stack.push(node);
  }
  return root.children;
}

export function parseEvidence(text) {
  return tree(markdown.parse(typeof text === 'string' ? text : '', {}));
}

export function inlineWords(nodes) {
  return nodes.map(node => node.type === 'softbreak' || node.type === 'hardbreak' ? '\n'
    : node.children?.length ? inlineWords(node.children) : node.content || '').join('');
}

export function evidenceLink(href, baseURL) {
  if (typeof href !== 'string' || !href.trim()) return null;
  try {
    const url = baseURL ? new URL(href, baseURL) : new URL(href);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function tableRows(node) {
  return node.children.flatMap(section => section.type === 'tr' ? [section.children]
    : section.children.filter(row => row.type === 'tr').map(row => row.children));
}

export function evidencePlainText(text) {
  function plain(nodes) {
    return nodes.map(node => {
      if (node.type === 'inline') return inlineWords(node.children);
      if (node.type === 'table') return tableRows(node).map(row => row.map(cell => plain(cell.children)).join(' | ')).join('\n');
      return node.children.length ? plain(node.children) : node.content;
    }).filter(Boolean).join('\n\n');
  }
  return plain(parseEvidence(text));
}
