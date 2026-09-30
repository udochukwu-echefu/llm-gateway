// Validate synthetic gateway SSE by structure, independent of JSON whitespace.
export function validStream(text, model) {
  let chunks = 0;
  let usage = false;
  let finished = false;
  let done = false;
  try {
    for (const line of text.split(/\r?\n/)) {
      if (!line.startsWith('data:')) continue;
      const data = line.slice(5).trim();
      if (done) return false;
      if (data === '[DONE]') { done = true; continue; }
      const value = JSON.parse(data);
      if (value.error || value.model !== model || !Array.isArray(value.choices)) return false;
      if (value.usage) {
        usage = value.usage.prompt_tokens === 10 && value.usage.completion_tokens === 20 && value.usage.total_tokens === 30;
        if (!usage) return false;
      }
      for (const choice of value.choices) {
        if (!choice.delta) return false;
        if (choice.delta.content) {
          if (choice.delta.content !== 'word ' || finished) return false;
          chunks += 1;
        }
        if (choice.finish_reason === 'stop') finished = true;
        else if (choice.finish_reason != null) return false;
      }
    }
  } catch (_) { return false; }
  return chunks === 20 && usage && finished && done;
}
