/**
 * tests/test_quant_engine_golden.js
 *
 * Golden-vector conformance test — JavaScript side.
 *
 * Extracts the QuantEngine module directly out of index.html (between the
 * QUANT_ENGINE_START/QUANT_ENGINE_END markers), evaluates it in an isolated
 * context (no DOM, no `state`, no other globals from index.html — QuantEngine
 * is a pure module and must not need any of those), then re-runs the SAME
 * tests/golden_vectors.json vectors used by the Python conformance test
 * (tests/test_quant_engine_golden.py) and asserts the outputs match within a
 * small numeric tolerance.
 *
 * Together with its Python sibling, this is the permanent safeguard against
 * the Python (canonical) and JavaScript (mirror) engines silently drifting
 * apart — see 04_Backend.md §15.
 *
 * No dependencies beyond Node's own standard library (fs, vm, assert, path).
 *
 * Run with:  node tests/test_quant_engine_golden.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const REPO_ROOT = path.resolve(__dirname, '..');
const INDEX_HTML = path.join(REPO_ROOT, 'index.html');
const VECTORS_PATH = path.join(__dirname, 'golden_vectors.json');

const TOL = 1e-9;

function approxEqual(actual, expected, label) {
  if (expected === null) {
    assert.strictEqual(actual, null, `${label}: expected null, got ${actual}`);
    return;
  }
  if (typeof expected === 'boolean') {
    assert.strictEqual(actual, expected, label);
    return;
  }
  const diff = Math.abs(actual - expected);
  const tolerance = TOL * Math.max(1, Math.abs(expected));
  assert.ok(
    diff <= tolerance,
    `${label}: expected ${expected}, got ${actual} (diff=${diff}, tolerance=${tolerance})`
  );
}

function extractQuantEngineSource() {
  const html = fs.readFileSync(INDEX_HTML, 'utf8');
  const startMarker = '// === QUANT_ENGINE_START ===';
  const endMarker = '// === QUANT_ENGINE_END ===';
  const startIdx = html.indexOf(startMarker);
  const endIdx = html.indexOf(endMarker);
  if (startIdx === -1 || endIdx === -1 || endIdx < startIdx) {
    throw new Error('Could not find QUANT_ENGINE_START/END markers in index.html — has the module been moved or renamed?');
  }
  return html.slice(startIdx, endIdx);
}

function loadQuantEngine() {
  const source = extractQuantEngineSource();
  const sandbox = {};
  vm.createContext(sandbox);
  vm.runInContext(source + '\nthis.__QuantEngine = QuantEngine;', sandbox);
  if (!sandbox.__QuantEngine) {
    throw new Error('QuantEngine did not evaluate to an object — extraction or module code may be broken.');
  }
  return sandbox.__QuantEngine;
}

function main() {
  const QuantEngine = loadQuantEngine();
  const vectors = JSON.parse(fs.readFileSync(VECTORS_PATH, 'utf8'));
  let checks = 0;

  for (const c of vectors.poisson_cdf) {
    approxEqual(QuantEngine.poissonCdf(c.k, c.lam), c.expected, `poissonCdf(${c.k}, ${c.lam})`);
    checks++;
  }

  for (const c of vectors.prob_over25) {
    approxEqual(QuantEngine.probOver25(c.lam_total), c.expected, `probOver25(${c.lam_total})`);
    checks++;
  }

  for (const c of vectors.btts_prob_diagnostics) {
    const result = QuantEngine.probBttsDiagnostics(c.lam_home, c.lam_away, c.adj);
    const keyMap = {
      raw_poisson: 'rawPoisson', base_adj_factor: 'baseAdjFactor', after_base_adj: 'afterBaseAdj',
      pen_ratio: 'penRatio', pen_gap: 'penGap', pen_smaller: 'penSmaller', pen_product: 'penProduct',
      total_penalty: 'totalPenalty', final_prob_unclamped: 'finalProbUnclamped',
      lam_ratio: 'lamRatio', lam_gap: 'lamGap', lam_product: 'lamProduct',
    };
    for (const [pyKey, jsKey] of Object.entries(keyMap)) {
      approxEqual(result[jsKey], c.expected[pyKey], `probBttsDiagnostics(${c.lam_home},${c.lam_away}).${jsKey}`);
      checks++;
    }
  }

  for (const c of vectors.prob_btts_yes_adjusted) {
    approxEqual(QuantEngine.probBttsAdjusted(c.lam_home, c.lam_away, c.adj), c.expected, `probBttsAdjusted(${c.lam_home},${c.lam_away})`);
    checks++;
  }

  for (const c of vectors.kelly_fraction) {
    approxEqual(QuantEngine.kellyFraction(c.p, c.odd), c.expected, `kellyFraction(${c.p},${c.odd})`);
    checks++;
  }

  for (const c of vectors.clamp_strength) {
    approxEqual(QuantEngine.clampStrength(c.x), c.expected, `clampStrength(${c.x})`);
    checks++;
  }
  for (const c of vectors.clamp_prob_o25) {
    approxEqual(QuantEngine.clampProbO25(c.prob), c.expected, `clampProbO25(${c.prob})`);
    checks++;
  }
  for (const c of vectors.clamp_prob_btts) {
    approxEqual(QuantEngine.clampProbBtts(c.prob), c.expected, `clampProbBtts(${c.prob})`);
    checks++;
  }
  for (const c of vectors.clamp_edge_o25) {
    approxEqual(QuantEngine.clampEdgeO25(c.edge), c.expected, `clampEdgeO25(${c.edge})`);
    checks++;
  }
  for (const c of vectors.clamp_edge_btts) {
    approxEqual(QuantEngine.clampEdgeBtts(c.edge), c.expected, `clampEdgeBtts(${c.edge})`);
    checks++;
  }

  for (const c of vectors.confidence_factor) {
    approxEqual(QuantEngine.confidenceFactor(c.edge, c.scale), c.expected, `confidenceFactor(${c.edge},${c.scale})`);
    checks++;
  }

  for (const c of vectors.fair_odds) {
    approxEqual(QuantEngine.fairOdds(c.prob_model), c.expected, `fairOdds(${c.prob_model})`);
    checks++;
  }

  for (const c of vectors.expected_value) {
    approxEqual(QuantEngine.expectedValue(c.prob_model, c.odd, c.stake), c.expected, `expectedValue(${c.prob_model},${c.odd},${c.stake})`);
    checks++;
  }

  for (const c of vectors.apply_lambda_boost) {
    const result = QuantEngine.applyLambdaBoost(c.lam_home, c.lam_away, c.boost);
    approxEqual(result.lamHome, c.expected.lam_home, `applyLambdaBoost(${c.lam_home},${c.lam_away},${c.boost}).lamHome`);
    approxEqual(result.lamAway, c.expected.lam_away, `applyLambdaBoost(${c.lam_home},${c.lam_away},${c.boost}).lamAway`);
    approxEqual(result.lamTotal, c.expected.lam_total, `applyLambdaBoost(${c.lam_home},${c.lam_away},${c.boost}).lamTotal`);
    checks += 3;
  }

  for (const c of vectors.weighted_mean) {
    approxEqual(QuantEngine.weightedMean(c.values, c.decay), c.expected, `weightedMean([${c.values}],${c.decay})`);
    checks++;
  }

  for (const c of vectors.compute_lambdas) {
    const result = QuantEngine.computeLambdas(c.history, c.home, c.away, {
      window: c.window, decay: c.decay, minGamesHome: c.min_games_home, minGamesAway: c.min_games_away,
    });
    approxEqual(result.lamHome, c.expected.lam_home, `computeLambdas(${c.label}).lamHome`);
    approxEqual(result.lamAway, c.expected.lam_away, `computeLambdas(${c.label}).lamAway`);
    approxEqual(result.lamTotal, c.expected.lam_total, `computeLambdas(${c.label}).lamTotal`);
    checks += 3;
  }

  console.log(`ALL GOLDEN VECTOR CHECKS PASSED (${checks} assertions across ${Object.keys(vectors).length} functions)`);
}

main();
