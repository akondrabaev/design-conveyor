// Cloudflare Worker: relay for the Gemini API, for servers in regions Google does not serve.
// The app sends its usual Gemini requests to https://<worker>.workers.dev/... with the header X-Relay-Secret;
// the worker forwards them to generativelanguage.googleapis.com and streams the answer back.
//
// GET /__where (with the secret) shows where the worker runs: if it runs in an unsupported region,
// Google may still answer "User location is not supported" - see README.md next to this file.

const UPSTREAM = 'https://generativelanguage.googleapis.com';
const DROP = ['host', 'x-relay-secret', 'x-forwarded-for', 'x-forwarded-proto', 'x-real-ip', 'cf-connecting-ip', 'cf-ipcountry', 'cf-ray', 'cf-visitor'];

export default {
  async fetch(request, env) {
    if (!env.RELAY_SECRET || request.headers.get('X-Relay-Secret') !== env.RELAY_SECRET) {
      return new Response('forbidden', { status: 403 });
    }
    const url = new URL(request.url);
    if (url.pathname === '/__where') {
      const trace = await (await fetch('https://www.cloudflare.com/cdn-cgi/trace')).text();
      return new Response(`client colo: ${request.cf && request.cf.colo}\nworker trace:\n${trace}`);
    }
    const headers = new Headers(request.headers);
    for (const h of DROP) headers.delete(h);
    return fetch(UPSTREAM + url.pathname + url.search, {
      method: request.method,
      headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
    });
  },
};
