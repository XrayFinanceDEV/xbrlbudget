// Export presentation metadata from the existing catalogs, never financial data.
// Usage: node tools/final_report/export_catalog.cjs [--check]
const fs = require('fs'), path = require('path'), Module = require('module');
const root = path.resolve(__dirname, '../..');
const ts = require(require.resolve('typescript', {paths: [path.join(root, 'frontend'), ...require.resolve.paths('typescript')]}));
Module._extensions['.ts'] = (m, f) => m._compile(ts.transpileModule(fs.readFileSync(f, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText, f);
const resolve = Module._resolveFilename;
Module._resolveFilename = function(request, ...args) { return resolve.call(this, request.startsWith('@/') ? path.join(root, 'frontend', request.slice(2)) : request, ...args); };
const catalog = require(path.join(root, 'frontend/lib/ivcee-catalog.ts'));
const indicators = require(path.join(root, 'frontend/lib/pratica-indicators.ts'));
const slug = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
function rows(input, statement) {
  const counts = new Map(); let section = null, currentAggregate = null;
  const output = input.map(r => {
    const dependencies = [];
    if (r.computed) r.computed(new Proxy({}, {get: (_, key) => {dependencies.push(key); return 0;}}));
    const base = r.field || (dependencies.length ? dependencies.join('+') : slug(r.label));
    const occurrence = (counts.get(base) || 0) + 1; counts.set(base, occurrence);
    const id = statement + ':' + base + (occurrence > 1 ? ':' + occurrence : '');
    const kind = !r.field && !r.computed ? (r.isTotal || r.isSubtotal ? 'section' : r.label.startsWith('10)') ? 'group' : 'detail') : r.isTotal ? 'total' : r.isSubtotal ? 'subtotal' : 'detail';
    let parent = kind === 'section' ? null : section;
    if (r.indent && r.field && /^(sp|ce)\d{2}[a-z]_/.test(r.field) && currentAggregate && (currentAggregate.includes(r.field.slice(0, 4) + '_') || currentAggregate.includes('10_ammortamenti'))) parent = currentAggregate;
    if (statement === 'balance_sheet' && r.field && /^(sp16|sp17)[a-z]_/.test(r.field) && currentAggregate) parent = currentAggregate;
    if (kind === 'section') { section = id; currentAggregate = null; }
    else if (kind === 'group') currentAggregate = id;
    else if (dependencies.length === 2 && dependencies.every(d => /^sp(16|17)[a-z]_/.test(d))) currentAggregate = id;
    else if (r.field && /^(sp|ce)\d{2}_/.test(r.field)) currentAggregate = id;
    return {id, code: r.field || id.split(':').slice(1).join(':'), label: r.label, parent_id: parent, level: parent === null ? 0 : parent === section ? 1 : 2, kind, field: r.field || null, dependencies, difference: r.label === 'DIFFERENZA (Attivo - Passivo)'};
  });
  // The presentation catalogs flatten layout indentation. Explicit economic
  // parentage must also distinguish overall results from the last subgroup.
  let rootHeading = null, logicalSection = null, debtGroup = null;
  const fields = new Map(), levels = new Map();
  for (const row of output) {
    if (statement === 'balance_sheet') {
      if (['ATTIVO', 'PASSIVO E PATRIMONIO NETTO'].includes(row.label)) {rootHeading = row.id; row.parent_id = null; logicalSection = null;}
      else if (row.kind === 'section') {row.parent_id = rootHeading; logicalSection = row.id; debtGroup = null;}
      else {
        row.parent_id = logicalSection || rootHeading;
        const accountParent = row.field && catalog.voce(row.field)?.parent;
        if (accountParent && fields.has(accountParent)) row.parent_id = fields.get(accountParent);
        if (row.dependencies.length === 2 && row.dependencies.every(d => /^sp(16|17)[a-z]_/.test(d))) {debtGroup = row.id;}
        else if (row.field && /^sp(16|17)[a-z]_/.test(row.field) && debtGroup) row.parent_id = debtGroup;
        if (['total_assets'].includes(row.field) || row.label === 'TOTALE PASSIVO E PATRIMONIO NETTO') row.parent_id = rootHeading;
        if (row.difference) row.parent_id = null;
        if (row.field === 'sp10_ratei_risconti_attivi' || row.field === 'sp18_ratei_risconti_passivi' || row.field === 'sp14_fondi_rischi' || row.field === 'sp15_tfr') row.parent_id = rootHeading;
      }
    } else {
      if (row.kind === 'section') {row.parent_id = null; logicalSection = row.id;}
      else {
        row.parent_id = logicalSection;
        const accountParent = row.field && catalog.voce(row.field)?.parent;
        if (accountParent && fields.has(accountParent)) row.parent_id = fields.get(accountParent);
        if (row.field?.startsWith('ce09')) row.parent_id = output.find(r => r.kind === 'group' && r.label.startsWith('10)'))?.id || logicalSection;
        if (row.label.includes('quiescenza')) row.parent_id = fields.get('ce08_costi_personale') || logicalSection;
        if (['ebitda', 'ebit', 'profit_before_tax', 'net_profit', 'ce20_imposte'].includes(row.field)) row.parent_id = null;
      }
    }
    row.level = row.parent_id === null ? 0 : levels.get(row.parent_id) + 1;
    if (!Number.isInteger(row.level)) throw new Error(`Unknown preceding parent for ${row.id}`);
    levels.set(row.id, row.level);
    if (row.field) fields.set(row.field, row.id);
  }
  return output;
}
const cf = fs.readFileSync(path.join(root, 'frontend/components/report/report-cashflow.tsx'), 'utf8').split('const CF_ROWS:')[1].split('const cfConfig')[0];
let cfSection = null, cfGroup = null;
const cashflow = [...cf.matchAll(/\{ label: "([^"]+)",(?: get: \(cf\) => cf\.([a-z_\.]+),)? kind: "([a-z]+)" \}/g)].map(m => {
  const id = 'cashflow:' + (m[2] || slug(m[1]));
  const parent = m[3] === 'section' ? null : m[3] === 'group' ? cfSection : cfGroup || cfSection;
  if (m[3] === 'section') {cfSection = id; cfGroup = null;}
  if (m[3] === 'group') cfGroup = id;
  return {id, code: m[2] || slug(m[1]), label: m[1], parent_id: parent, level: parent === null ? 0 : parent === cfSection ? 1 : 2, kind: m[3], field: m[2] || null, dependencies: [], difference: false};
});
for (const row of cashflow) {
  if (row.field?.startsWith('cash_reconciliation.')) {row.parent_id = null; row.level = 0;}
  else if (['operating.cashflow_before_wc', 'operating.cashflow_after_wc', 'operating.total_operating_cashflow'].includes(row.field)) {row.parent_id = cashflow[0].id; row.level = 1;}
}
const ratioSrc = fs.readFileSync(path.join(root, 'frontend/components/report/report-ratios.tsx'), 'utf8');
const ratios = [...ratioSrc.matchAll(/key: "([^"]+)", label: "([^"]+)", category: "([^"]+)", format: "([^"]+)"/g)].map(m => ({key: m[1], label: m[2], category: m[3], format: m[4]}));
if (!cashflow.length || !ratios.length) throw new Error('Catalog extraction failed');
const data = {catalog_version: '1', income_statement: rows(catalog.INCOME_STATEMENT_ROWS, 'income_statement'), balance_sheet: rows(catalog.BALANCE_STATEMENT_ROWS, 'balance_sheet'), cashflow, practice_indicators: indicators.INDICATOR_DEFS.map(({key, label, format}) => ({key, label, format})), analytical_indicators: ratios};
const target = path.join(root, 'contracts/final_report_dossier_catalog.json');
const output = JSON.stringify(data, null, 2) + '\n';
if (process.argv.includes('--check')) {if (fs.readFileSync(target, 'utf8') !== output) throw new Error('Dossier catalog is out of sync; regenerate it');}
else fs.writeFileSync(target, output);
process.stdout.write(`Dossier catalog ${process.argv.includes('--check') ? 'checked' : 'exported'}\n`);
