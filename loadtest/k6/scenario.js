import http from 'k6/http';
import { validStream } from './stream-validation.js';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const scenario = __ENV.SCENARIO || 'smoke';
const base = __ENV.TARGET || 'http://gateway-loadtest-1:8000';
const direct = scenario === 'provider';
const key = direct ? '' : open(`/credentials/${__ENV.KEY_FILE}`).trim();
const rate = Number(__ENV.RATE || 5);
const duration = __ENV.DURATION || '30s';
const stream = scenario === 'S2';
const embedding = scenario === 'S5';
const good = new Counter('successful_requests');
const rejected = new Counter('limited_requests');
const errors = new Rate('unexpected_errors');
const cache = new Rate('cache_hits');
const clientLatency = new Trend('client_latency', true);
const firstByte = new Trend('first_byte_latency', true);
const acceptedAt = new Trend('admitted_at', false);

http.setResponseCallback(http.expectedStatuses(200, ...(scenario === 'S6' ? [429] : [])));
export const options = {
  scenarios: { benchmark: {
    executor: 'constant-arrival-rate', rate, timeUnit: '1s', duration,
    preAllocatedVUs: Math.max(10, Math.ceil(rate * (stream ? 1.5 : 0.4))),
    maxVUs: Math.max(30, Math.ceil(rate * (stream ? 3 : 1.5))),
    gracefulStop: '30s',
  } },
  summaryTrendStats: ['avg', 'min', 'med', 'p(50)', 'p(95)', 'p(99)', 'max'],
  thresholds: { unexpected_errors: ['rate==0'], dropped_iterations: ['count==0'] },
};

const piiLine = 'Email ada@example.com phone +1 (415) 555-0100 card 4242 4242 4242 4242 IBAN GB82 WEST 1234 5698 7654 32 IP 192.0.2.1. ';
const prompt = scenario === 'S4' ? piiLine.repeat(Math.ceil(5120 / piiLine.length)).slice(0, 5120) : 'Return a short synthetic answer.';
const model = direct ? 'openai/gpt-oss-20b' : embedding ? 'openai/text-embedding-3-small' : 'groq/openai/gpt-oss-20b';
const body = JSON.stringify(embedding ? {model, input: 'unchanging synthetic document'} : {
  model, messages: [{role: 'user', content: prompt}], stream,
  ...(stream ? {stream_options: {include_usage: true}} : {}),
});
const headers = {'Content-Type': 'application/json', 'x-lgw-cache': embedding ? 'enabled' : 'disabled'};
if (!direct) headers.Authorization = `Bearer ${key}`;

export default function () {
  const response = http.post(`${base}/v1/${embedding ? 'embeddings' : 'chat/completions'}`, body, {headers: {...headers, 'x-request-id': `${__ENV.OUTPUT}-request-${__VU}-${__ITER}`}, timeout: '90s'});
  let valid = response.status === 200;
  if (valid && stream) {
    valid = validStream(String(response.body), model);
  } else if (valid) {
    try {
      const value = JSON.parse(String(response.body));
      valid = value.model === model && !!value.usage && (embedding ? value.data.length === 1 : value.choices[0].finish_reason === 'stop');
    } catch (_) { valid = false; }
  }
  const limited = scenario === 'S6' && response.status === 429 && String(response.body).includes('rate_limit_exceeded');
  errors.add(!valid && !limited);
  check(response, {'valid success or expected RPM rejection': () => valid || limited});
  clientLatency.add(response.timings.duration);
  firstByte.add(response.timings.waiting);
  if (valid) {
    good.add(1);
    acceptedAt.add(Number(response.headers['X-Ratelimit-Reset-Requests'] || 0));
    if (embedding) cache.add(response.headers['X-Lgw-Cache'] === 'hit');
  }
  if (limited) rejected.add(1);
}

export function handleSummary(data) {
  return { [`/results/${__ENV.OUTPUT}/summary.json`]: JSON.stringify(data, null, 2) };
}
