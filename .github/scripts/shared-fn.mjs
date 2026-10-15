// PR files are data: a virtual compiler host never reads the checkout or loads plugins.
// Adapted from archive/2026-10-14-pr-review-bakeoff/round2/seeds/shared-fn.mjs.
import {createRequire} from 'node:module';
import {execFileSync, spawn} from 'node:child_process';
import {Worker, isMainThread, parentPort, workerData} from 'node:worker_threads';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const LIMIT = 64 * 1024 * 1024;
const TIMEOUT = 120000;
const source = /\.(?:tsx?|jsx?|mjs|cjs)$/i;
const skipped = /(^|\/)(node_modules|dist|build|\.next|coverage)(\/|$)/;
const normal = p => p.replaceAll('\\', '/');
const root = '/__pr_snapshot__';

function git(...args) {
  return execFileSync('git', args, {encoding: 'utf8', timeout: TIMEOUT, windowsHide: true, maxBuffer: LIMIT});
}

async function archive(ref, budget) {
  const child = spawn('git', ['archive', '--format=tar', ref], {windowsHide: true, timeout: TIMEOUT});
  const chunks = []; let bytes = 0, error = '';
  child.stderr.on('data', b => { error += b.toString().slice(0, 2000); });
  return await new Promise((resolve, reject) => {
    let overflow = false;
    child.stdout.on('data', chunk => {
      bytes += chunk.length;
      if (bytes > budget) { overflow = true; child.kill(); }
      else chunks.push(chunk);
    });
    child.on('error', reject);
    child.on('close', code => {
      if (overflow) return reject(Error('64 MB combined archive limit exceeded'));
      if (code !== 0) return reject(Error(`git archive failed: ${error}`));
      try { resolve({files: unpack(Buffer.concat(chunks)), bytes}); } catch (e) { reject(e); }
    });
  });
}

function unpack(tar) {
  const files = new Map(); let pax = {}, longName;
  for (let offset = 0; offset + 512 <= tar.length;) {
    const h = tar.subarray(offset, offset + 512);
    const str = (a, b) => h.subarray(a, b).toString().split('\0')[0];
    const name = str(0, 100); if (!name) break;
    const size = parseInt(str(124, 136).trim() || '0', 8);
    if (!Number.isSafeInteger(size) || size < 0 || offset + 512 + size > tar.length) throw Error('Invalid tar member');
    const content = tar.subarray(offset + 512, offset + 512 + size);
    const type = str(156, 157);
    const file = pax.path || longName || (str(345, 500) ? str(345, 500) + '/' : '') + name;
    if (type === 'x' || type === 'g') {
      let pos = 0;
      while (pos < content.length) {
        const space = content.indexOf(32, pos), length = Number(content.subarray(pos, space).toString());
        if (!length || length < 3) throw Error('Invalid pax header');
        const row = content.subarray(space + 1, pos + length - 1).toString(), eq = row.indexOf('=');
        pax[row.slice(0, eq)] = row.slice(eq + 1); pos += length;
      }
    } else if (type === 'L') longName = content.toString().replace(/\0.*$/s, '');
    else {
      if ((type === '0' || type === '') && !skipped.test(file) && (source.test(file) || /(^|\/)(tsconfig|jsconfig)(\.[^/]*)?\.json$/.test(file))) files.set(file, content.toString('utf8'));
      pax = {}; longName = undefined;
    }
    offset += 512 + Math.ceil(size / 512) * 512;
  }
  return files;
}

function graph(files, ts) {
  const absolute = new Map([...files].map(([f, text]) => [root + '/' + f, text]));
  const norm = p => path.posix.normalize(normal(p));
  const fileExists = p => absolute.has(norm(p));
  const readFile = p => absolute.get(norm(p));
  const directories = new Set();
  for (const file of absolute.keys()) {
    for (let dir = path.posix.dirname(file); !directories.has(dir); dir = path.posix.dirname(dir)) {
      directories.add(dir);
      if (dir === path.posix.dirname(dir)) break;
    }
  }
  const directoryExists = p => directories.has(norm(p));
  const defaults = {target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, jsx: ts.JsxEmit.Preserve,
    allowJs: true, checkJs: true, noLib: true, types: [], skipLibCheck: true};
  const configs = new Map();
  const configHost = {useCaseSensitiveFileNames: true, fileExists, readFile, directoryExists,
    readDirectory: () => [], getCurrentDirectory: () => root};
  for (const [f, text] of absolute) {
    if (!/(^|\/)(tsconfig|jsconfig)\.json$/.test(f)) continue;
    const json = ts.parseConfigFileTextToJson(f, text);
    if (json.error) throw Error(`Invalid config: ${f}`);
    // parseJsonConfigFileContent reads extends and paths through the data-only host.
    const parsed = ts.parseJsonConfigFileContent(json.config, configHost, path.posix.dirname(f), {}, f);
    // Missing extends targets cannot be installed or read outside this snapshot.
    // Retain local options; malformed JSON/options and config cycles still fail.
    const errors = parsed.errors.filter(e => e.code !== 18003 && e.code !== 18002 && e.code !== 5083 && e.code !== 6053);
    if (errors.length) throw Error(ts.flattenDiagnosticMessageText(errors[0].messageText, '\n'));
    configs.set(path.posix.dirname(f), {...defaults, ...parsed.options, allowJs: true, noLib: true, types: []});
  }
  function optionsFor(file) {
    let dir = path.posix.dirname(norm(file));
    while (dir.startsWith(root)) {
      if (configs.has(dir)) return configs.get(dir);
      dir = path.posix.dirname(dir);
    }
    return defaults;
  }
  const groups = new Map(), definitions = new Map(), references = new Map();
  for (const file of absolute.keys()) {
    if (!source.test(file)) continue;
    const options = optionsFor(file);
    if (!groups.has(options)) groups.set(options, []);
    groups.get(options).push(file);
  }
  // Each project's module mode controls binding as well as import resolution.
  // Declarations and caller files are merged across projects by snapshot identity.
  for (const [options, roots] of groups) {
  const host = ts.createCompilerHost(options);
  Object.assign(host, {fileExists, readFile, directoryExists, getDirectories: () => [],
    realpath: norm, getCurrentDirectory: () => root,
    getSourceFile: (p, language) => fileExists(p) ? ts.createSourceFile(p, readFile(p), language, true) : undefined,
    resolveModuleNames: (names, containing) => names.map(name => ts.resolveModuleName(name, containing, optionsFor(containing), host).resolvedModule)});
  const program = ts.createProgram(roots, options, host);
  const checker = program.getTypeChecker();
  function exportsOf(module) {
    const exports = checker.getExportsOfModule(module);
    // getExportsOfModule omits the callable value assigned to module.exports.
    const direct = module.exports?.get('export=');
    return direct && !exports.includes(direct) ? [...exports, direct] : exports;
  }
  function canonical(s) {
    const seen = new Set();
    while (s && (s.flags & ts.SymbolFlags.Alias) && !seen.has(s)) { seen.add(s); s = checker.getAliasedSymbol(s); }
    return s;
  }
  function declaration(s, seen = new Set()) {
    s = canonical(s);
    if (!s || seen.has(s)) return;
    seen.add(s);
    for (const d of s.declarations || []) {
      // Destructuring require() does not get SymbolFlags.Alias, unlike ESM imports.
      const variable = ts.isBindingElement(d) ? d.parent.parent : ts.isVariableDeclaration(d) ? d : null;
      const init = variable?.initializer;
      if (init && ts.isCallExpression(init) && init.expression.getText() === 'require' && init.arguments.length === 1) {
        const module = checker.getSymbolAtLocation(init.arguments[0]);
        const name = ts.isBindingElement(d) ? (d.propertyName || d.name).getText() : 'export=';
        const exported = module && exportsOf(module).find(x => x.name === name);
        const target = declaration(exported, seen);
        if (target) return target;
      }
    }
    const d = s.declarations?.find(d => ts.isFunctionDeclaration(d) && d.body) || s.declarations?.find(d => ts.isFunctionDeclaration(d) ||
      ((ts.isVariableDeclaration(d) || ts.isPropertyAssignment(d) || ts.isPropertyAccessExpression(d) || ts.isBinaryExpression(d)) &&
        checker.getTypeAtLocation(d).getCallSignatures().length));
    // Include the RHS body of exports.f = function/arrow when comparing changes.
    return d && ts.isPropertyAccessExpression(d) && ts.isBinaryExpression(d.parent) && d.parent.left === d ? d.parent : d;
  }
  const fileOf = d => d.getSourceFile().fileName.slice(root.length + 1);
  const identity = d => `${fileOf(d)}::${d.pos}:${d.end}`;
  for (const sf of program.getSourceFiles()) {
    // Plain .js CommonJS files have a bound module symbol but no ESM indicator,
    // so getSymbolAtLocation(SourceFile) returns undefined for them.
    const module = checker.getSymbolAtLocation(sf) || (sf.commonJsModuleIndicator && sf.symbol);
    if (!module) continue;
    for (const symbol of exportsOf(module)) {
      const d = declaration(symbol); if (!d) continue;
      const own = d.getSourceFile(), file = fileOf(d);
      if (!files.has(file)) continue;
      const name = d.name?.getText(own) || (ts.isBinaryExpression(d) && d.right.name?.getText(own)) || symbol.name;
      // Stable comparison key; position is used only for linking references in one graph.
      definitions.set(identity(d), {file, function: name, text: d.getText(own),
        start: own.getLineAndCharacterOfPosition(d.getStart(own)).line + 1,
        end: own.getLineAndCharacterOfPosition(d.end).line + 1});
    }
  }
  for (const sf of program.getSourceFiles()) {
    const file = fileOf(sf);
    function visit(n) {
      if (ts.isIdentifier(n)) {
        const d = declaration(checker.getSymbolAtLocation(n));
        let p = n.parent, binding = false;
        while (p && !ts.isSourceFile(p)) {
          if (ts.isImportDeclaration(p) || ts.isExportDeclaration(p) ||
              (ts.isVariableDeclaration(p) && p.initializer && ts.isCallExpression(p.initializer) && p.initializer.expression.getText(sf) === 'require') ||
              (ts.isCallExpression(p) && p.expression.getText(sf) === 'require')) { binding = true; break; }
          p = p.parent;
        }
        if (d && !binding && d.name !== n) {
          const id = identity(d), def = definitions.get(id);
          if (def && file !== def.file) {
            if (!references.has(id)) references.set(id, new Map());
            const refs = references.get(id);
            if (!refs.has(file)) refs.set(file, []);
            refs.get(file).push(sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1);
          }
        }
      }
      ts.forEachChild(n, visit);
    }
    visit(sf);
  }
  }
  return new Map([...definitions].map(([id, def]) => [`${def.file}::${def.function}`, {...def,
    callers: [...(references.get(id) || new Map())].map(([file, lines]) => ({file, lines: [...new Set(lines)]}))}]));
}

async function detect(baseRef, headRef) {
  if (!baseRef || !headRef || !/^[a-f0-9]{40,64}$/i.test(baseRef) || !/^[a-f0-9]{40,64}$/i.test(headRef)) throw Error('Usage: shared-fn.mjs <base_sha> <head_sha> (full commit IDs)');
  const base = git('rev-parse', '--verify', `${baseRef}^{commit}`).trim();
  const head = git('rev-parse', '--verify', `${headRef}^{commit}`).trim();
  const mergeBase = git('merge-base', base, head).trim();
  const before = await archive(mergeBase, LIMIT);
  const after = await archive(head, LIMIT - before.bytes);
  const require = createRequire(import.meta.url), ts = require(process.env.TS_PATH || 'typescript');
  const a = graph(before.files, ts), b = graph(after.files, ts), result = [];
  for (const key of new Set([...a.keys(), ...b.keys()])) {
    const old = a.get(key), next = b.get(key);
    if (old?.text === next?.text) continue;
    const def = (old?.callers.length || 0) >= (next?.callers.length || 0) ? old : next;
    if (!def || def.callers.length < 2) continue;
    const {text, ...entry} = def;
    result.push({...entry, change: !old ? 'added-or-renamed' : !next ? 'deleted-or-renamed' : 'changed'});
  }
  return {base_sha: base, head_sha: head, merge_base: mergeBase,
    detector: result.length ? 'matched' : 'not-matched', shared_functions: result.sort((a,b) => a.file.localeCompare(b.file) || a.function.localeCompare(b.function))};
}

if (!isMainThread) {
  detect(...workerData).then(result => parentPort.postMessage({result})).catch(e => parentPort.postMessage({error: e.message}));
} else if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // The supervisor remains responsive even if parsing or symbol resolution stalls.
  const worker = new Worker(new URL(import.meta.url), {workerData: process.argv.slice(2)});
  let finished = false;
  const finish = (code, value) => {
    if (finished) return; finished = true; clearTimeout(timer);
    console.log(JSON.stringify(value)); process.exitCode = code; worker.terminate();
  };
  const timer = setTimeout(() => finish(2, {detector: 'error', error: '2 minute detector deadline exceeded'}), TIMEOUT);
  worker.on('message', ({result, error}) => error ? finish(2, {detector: 'error', error}) : finish(result.shared_functions.length ? 0 : 1, result));
  worker.on('error', e => finish(2, {detector: 'error', error: e.message}));
  worker.on('exit', code => { if (!finished) finish(2, {detector: 'error', error: `Detector worker exited unexpectedly (${code})`}); });
}
