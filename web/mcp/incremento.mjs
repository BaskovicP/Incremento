// Dependency-free stdio transport for Claude Desktop's bundled Node runtime.
// MCP messages are forwarded unchanged to Incremento's loopback-only endpoint.
import http from 'node:http';
import { pathToFileURL } from 'node:url';

const MAX_INPUT = 65536;
const MAX_OUTPUT = 512 * 1024;

export function forward(message, { token, port = 8767, version = '2025-11-25' }) {
  return new Promise((resolve, reject) => {
    if (!token || !/^[A-Za-z0-9_-]+$/.test(token)) {
      reject(new Error('Configure the connection token from Incremento → AI connections.'));
      return;
    }
    const body = JSON.stringify(message);
    if (Buffer.byteLength(body) > MAX_INPUT) {
      reject(new Error('MCP request is too large.'));
      return;
    }
    const request = http.request({
      hostname: '127.0.0.1', port, path: '/mcp', method: 'POST',
      headers: {
        'Content-Type': 'application/json', Accept: 'application/json, text/event-stream',
        Authorization: `Bearer ${token}`, 'MCP-Protocol-Version': version,
        'Content-Length': Buffer.byteLength(body),
      },
    }, (response) => {
      const chunks = [];
      let size = 0;
      response.on('data', (chunk) => {
        size += chunk.length;
        if (size > MAX_OUTPUT) response.destroy(new Error('MCP response is too large.'));
        else chunks.push(chunk);
      });
      response.on('error', reject);
      response.on('end', () => {
        if (response.statusCode === 202) { resolve(null); return; }
        if (response.statusCode !== 200) {
          reject(new Error(`Incremento connection failed (HTTP ${response.statusCode}). Check AI connections in Anki.`));
          return;
        }
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
        catch { reject(new Error('Invalid response from Incremento.')); }
      });
    });
    request.setTimeout(60000, () => request.destroy(new Error('Incremento request timed out; retry writes with the same request_id.')));
    request.on('error', (error) => reject(new Error(error.code === 'ECONNREFUSED'
      ? 'Open Anki on the paired profile and enable Incremento → AI connections.'
      : 'Incremento connection interrupted; check current state before retrying a write.')));
    request.end(body);
  });
}

export function run(input = process.stdin, output = process.stdout, token = process.env.INCREMENTO_MCP_TOKEN) {
  let buffer = Buffer.alloc(0);
  let queue = Promise.resolve();
  let version = '2025-11-25';
  input.on('data', (chunk) => {
    // Backpressure limits us to one input chunk and one HTTP operation; a
    // client cannot accumulate an unbounded queue while Anki is busy.
    input.pause();
    queue = queue.then(async () => {
      buffer = Buffer.concat([buffer, Buffer.from(chunk)]);
      let end;
      while ((end = buffer.indexOf(10)) >= 0) {
        const line = buffer.subarray(0, end);
        buffer = buffer.subarray(end + 1);
        if (!line.length) continue;
        if (line.length > MAX_INPUT) { input.destroy(); return; }
        let message;
        try { message = JSON.parse(line.toString('utf8')); }
        catch { output.write(JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Invalid JSON.' } }) + '\n'); continue; }
        try {
          const reply = await forward(message, { token, version });
          if (reply) {
            if (message?.method === 'initialize' && reply.result?.protocolVersion) version = reply.result.protocolVersion;
            output.write(JSON.stringify(reply) + '\n');
          }
        } catch (error) {
          if (message && Object.hasOwn(message, 'id')) output.write(JSON.stringify({ jsonrpc: '2.0', id: message.id,
            error: { code: -32603, message: error.message } }) + '\n');
        }
      }
      if (buffer.length > MAX_INPUT) input.destroy();
      else input.resume();
    });
  });
  return () => queue;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) run();
