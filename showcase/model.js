/* Small deterministic models for the public method illustrations. */
(function (root) {
  'use strict';
  function sampleRows(total, count, random = true) {
    if (!Number.isInteger(total) || !Number.isInteger(count) || total < 1 || count < 1) throw new RangeError('Invalid sample bounds');
    const selected = new Map();
    const width = Math.min(count, total);
    const starts = [0, Math.max(0, Math.floor((total - width) / 2)), Math.max(0, total - width)];
    starts.forEach(start => { for (let i = start; i < start + width; i++) selected.set(i, 'stratified'); });
    if (random) {
      let seed = 42;
      const remaining = Array.from({length: total}, (_, i) => i).filter(i => !selected.has(i));
      for (let i = 0; i < 6 && remaining.length; i++) {
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        const index = seed % remaining.length;
        selected.set(remaining.splice(index, 1)[0], 'random');
      }
    }
    return selected;
  }
  function chunkRows(rows, size) {
    if (!Number.isInteger(size) || size < 1) throw new RangeError('Invalid chunk size');
    const chunks = [];
    for (let i = 0; i < rows.length; i += size) chunks.push(rows.slice(i, i + size));
    return chunks;
  }
  function classifyIdentity(a, b) {
    if (a.code && b.code && a.code !== b.code) return 'conflict';
    if (a.code && b.code && a.code === b.code) return 'same';
    if (a.name && a.name === b.name && a.address && a.address === b.address) return 'same';
    return 'uncertain';
  }
  const api = { sampleRows, chunkRows, classifyIdentity };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.BEIModel = api;
})(typeof globalThis === 'undefined' ? this : globalThis);
