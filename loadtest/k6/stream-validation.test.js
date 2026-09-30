// Pure k6 regression checks: this script makes no HTTP calls.
import { validStream } from './stream-validation.js';

export const options = { vus: 1, iterations: 1 };
const model = 'groq/openai/gpt-oss-20b';
const chunk = {model, choices: [{delta: {content: 'word '}, finish_reason: null}]};
const finish = {model, choices: [{delta: {}, finish_reason: 'stop'}]};
const usage = {model, choices: [], usage: {prompt_tokens: 10, completion_tokens: 20, total_tokens: 30}};
const event = value => `data: ${JSON.stringify(value)}\n\n`;
const stream = count => Array(count).fill(event(chunk)).join('') + event(finish) + event(usage) + 'data: [DONE]\n\n';
function expect(condition, name) {
  if (!condition) throw new Error(name);
}
export default function () {
  const compact = stream(20);
  const spaced = compact.replace(/"content":/g, '"content": ');
  expect(validStream(compact, model), 'compact stream rejected');
  expect(validStream(spaced, model), 'valid spaced JSON stream rejected');
  expect(!validStream(stream(19), model), 'missing chunk accepted');
  expect(!validStream(stream(21), model), 'extra chunk accepted');
  expect(!validStream(compact.replace('data: [DONE]\n\n', ''), model), 'missing DONE accepted');
  expect(!validStream(compact.replace(event(usage), ''), model), 'missing usage accepted');
  expect(!validStream(compact.replace(event(finish), ''), model), 'missing finish accepted');
  expect(!validStream(compact + event(chunk), model), 'data after DONE accepted');
  expect(!validStream(compact.replace('"word "', '"wrong"'), model), 'wrong content accepted');
  expect(!validStream(compact, 'wrong-model'), 'wrong model accepted');
  expect(!validStream('data: {bad JSON}\n\n', model), 'malformed JSON accepted');
  expect(!validStream(event({error: {code: 'synthetic'}}) + compact, model), 'error event accepted');
  console.log('12 stream validator regression checks passed; no HTTP calls.');
}
