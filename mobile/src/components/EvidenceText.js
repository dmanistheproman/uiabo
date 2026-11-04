import { colours, typography } from '../theme';
import { useMemo } from 'react';
import { Alert, Linking, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { evidenceLink, inlineWords, parseEvidence, tableRows } from '../utils/evidenceMarkdown';

async function openEvidenceLink(url) {
  try { await Linking.openURL(url); }
  catch { Alert.alert('Could not open website', 'Please try again when you are connected.'); }
}

function withoutSourceImages(nodes) {
  const visible = nodes.flatMap(node => {
    if (node.type === 'image') return [];
    if (!node.children.length) return [node];
    const children = withoutSourceImages(node.children);
    // Remove empty image-only paragraphs/links, preserving table cell alignment.
    if (!children.length && !['td', 'th', 'tr'].includes(node.type)) return [];
    return [{ ...node, children }];
  });
  const isBreak = node => node?.type === 'softbreak' || node?.type === 'hardbreak';
  while (isBreak(visible[0])) visible.shift();
  while (isBreak(visible.at(-1))) visible.pop();
  return visible;
}

function Inline({ nodes, baseURL }) {
  return nodes.map((node, index) => {
    if (node.type === 'softbreak' || node.type === 'hardbreak') return '\n';
    if (node.type === 'image') return null;
    const children = node.children.length ? <Inline nodes={node.children} baseURL={baseURL} /> : node.content;
    if (node.type === 'link') {
      const url = evidenceLink(node.attrs.href, baseURL);
      return <Text key={index} style={url && styles.link} accessibilityRole={url ? 'link' : undefined}
        accessibilityHint={url ? 'Opens the source website' : undefined}
        onPress={url ? () => openEvidenceLink(url) : undefined}>{children}</Text>;
    }
    return <Text key={index} style={styles[node.type]}>{children}</Text>;
  });
}

function EvidenceTable({ node, baseURL }) {
  const { fontScale } = useWindowDimensions();
  const rows = tableRows(node);
  const headers = rows[0]?.map(cell => inlineWords(cell.children)) || [];
  return <View style={styles.tableContainer}>
    <Text style={styles.tableHint}>Swipe sideways to read all columns.</Text>
    <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator
      accessibilityLabel="Source evidence table. Scroll horizontally for more columns."
      style={styles.tableScroll} contentContainerStyle={styles.tableContent}>
      <View style={styles.table}>
        {rows.map((row, rowIndex) => <View key={rowIndex} style={styles.row}>
          {row.map((cell, column) => <View key={column} style={[styles.cell,
            { width: (column === 0 ? 220 : 150) * Math.max(1, Math.min(fontScale, 1.6)) },
            cell.type === 'th' ? styles.headerCell : rowIndex % 2 === 0 && styles.alternateCell]}>
            <Text selectable accessibilityRole={cell.type === 'th' ? 'header' : 'text'}
              accessibilityLabel={cell.type === 'th' ? undefined : `${headers[column] || 'Column ' + (column + 1)}: ${inlineWords(cell.children)}`}
              style={[styles.body, cell.type === 'th' && styles.strong]}>
              <Inline nodes={cell.children.flatMap(child => child.type === 'inline' ? child.children : [child])} baseURL={baseURL} />
            </Text>
          </View>)}
        </View>)}
      </View>
    </ScrollView>
  </View>;
}

function Blocks({ nodes, baseURL, textStyle }) {
  return nodes.map((node, index) => {
    if (node.type === 'table') return <EvidenceTable key={index} node={node} baseURL={baseURL} />;
    if (node.type === 'bullet_list' || node.type === 'ordered_list') {
      return <View key={index} style={styles.blocks}>{node.children.map((item, itemIndex) =>
        <View key={itemIndex} style={styles.listItem}>
          <Text style={[styles.body, textStyle, styles.marker]}>{node.type === 'ordered_list' ? `${Number(node.attrs.start || 1) + itemIndex}.` : '\u2022'}</Text>
          <View style={styles.listContent}><Blocks nodes={item.children} baseURL={baseURL} textStyle={textStyle} /></View>
        </View>)}</View>;
    }
    if (node.type === 'blockquote') return <View key={index} style={[styles.blocks, styles.quote]}>
      <Blocks nodes={node.children} baseURL={baseURL} textStyle={textStyle} />
    </View>;
    if (node.type === 'hr') return <View key={index} style={styles.rule} />;
    if (node.type === 'paragraph' || node.type === 'heading') return <Text selectable key={index}
      accessibilityRole={node.type === 'heading' ? 'header' : 'text'}
      style={[styles.body, textStyle, node.type === 'heading' && styles.heading]}>
      <Inline nodes={node.children.flatMap(child => child.type === 'inline' ? child.children : [child])} baseURL={baseURL} />
    </Text>;
    if (node.type === 'fence' || node.type === 'code_block') return <Text selectable key={index} style={[styles.body, styles.code_inline]}>{node.content}</Text>;
    // Preserve unfamiliar syntax as readable text instead of dropping evidence.
    return node.children.length ? <View key={index} style={styles.blocks}><Blocks nodes={node.children} baseURL={baseURL} textStyle={textStyle} /></View>
      : <Text selectable key={index} style={[styles.body, textStyle]}>{node.content}</Text>;
  });
}

export default function EvidenceText({ children, baseURL, quoted = false, textStyle }) {
  const nodes = useMemo(() => withoutSourceImages(parseEvidence(children)), [children]);
  if (!nodes.length) return null;
  return <View style={[styles.blocks, quoted && styles.quote]}>
    <Blocks nodes={nodes} baseURL={baseURL} textStyle={textStyle} />
  </View>;
}

const styles = StyleSheet.create({
  blocks: { gap: 16, minWidth: 0, alignSelf: 'stretch' },
  body: { ...typography.body, color: colours.text, flexShrink: 1 },
  heading: { ...typography.heading, color: colours.ink },
  strong: { fontWeight: '700' },
  em: { fontStyle: 'italic' },
  s: { textDecorationLine: 'line-through' },
  code_inline: { fontFamily: 'monospace', backgroundColor: colours.background },
  link: { color: colours.blue, textDecorationLine: 'underline' },
  quote: { borderLeftWidth: 3, borderLeftColor: colours.blue, paddingLeft: 14 },
  rule: { borderTopWidth: 1, borderTopColor: colours.divider },
  listItem: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  marker: { minWidth: 24 },
  listContent: { flex: 1, gap: 12, minWidth: 0 },
  tableContainer: { gap: 12, minWidth: 0, alignSelf: 'stretch' },
  tableHint: { ...typography.secondary, color: colours.muted },
  tableScroll: { maxWidth: '100%' },
  tableContent: { paddingBottom: 12 },
  table: { borderTopWidth: 1, borderLeftWidth: 1, borderColor: colours.border },
  row: { flexDirection: 'row', alignItems: 'stretch' },
  cell: { padding: 14, borderRightWidth: 1, borderBottomWidth: 1, borderColor: colours.border, backgroundColor: colours.white },
  headerCell: { backgroundColor: colours.infoBackground },
  alternateCell: { backgroundColor: colours.background },
});
