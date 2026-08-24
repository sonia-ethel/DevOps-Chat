// Polyfill for Node versions missing crypto.hash used by Vite 7
const crypto = require("node:crypto");
if (!crypto.hash) {
  crypto.hash = (algorithm, data, encoding) => {
    return crypto.createHash(algorithm).update(data).digest(encoding);
  };
}
