import assert from 'node:assert/strict';
import http from 'node:http';
import { PassThrough } from 'node:stream';
import test from 'node:test';
import { forward, run } from '../web/mcp/incremento.mjs';

test('connector forwards MCP JSON with auth and accepts notifications without output', async () => {
  const seen = [];
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks));
    seen.push({ body, auth: req.headers.authorization, host: req.headers.host });
    if (!Object.hasOwn(body, 'id')) { res.writeHead(202).end(); return; }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ jsonrpc: '2.0', id: body.id, result: { tools: [] } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  try {
    const message = { jsonrpc: '2.0', id: 1, method: 'tools/list' };
    assert.deepEqual(await forward(message, { token: 'secret', port }), { jsonrpc: '2.0', id: 1, result: { tools: [] } });
    assert.equal(await forward({ jsonrpc: '2.0', method: 'notifications/initialized' }, { token: 'secret', port }), null);
    assert.deepEqual(seen[0], { body: message, auth: 'Bearer secret', host: `127.0.0.1:${port}` });
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('stdio reports invalid JSON and missing setup without printing the token', async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  let text = '';
  output.on('data', chunk => { text += chunk; });
  const settled = run(input, output, '');
  input.write('{broken\n{"jsonrpc":"2.0","id":2,"method":"initialize"}\n');
  await settled();
  const lines = text.trim().split('\n').map(JSON.parse);
  assert.equal(lines[0].error.code, -32700);
  assert.equal(lines[1].id, 2);
  assert.match(lines[1].error.message, /connection token/);
});
