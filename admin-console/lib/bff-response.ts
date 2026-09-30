import "server-only";
import { redactCredentials } from "./admin-client";

// Drop hashes and nested secrets; release only the initial creation's key field.
export function browserResponse(body: unknown,permitsKey: boolean): unknown {
  if(typeof body==="string") return redactCredentials(body);
  if(Array.isArray(body)) return body.map((item) => browserResponse(item,false));
  if(body&&typeof body==="object") {
    const entries=Object.entries(body)
      .filter(([key]) => key!=="secret_hash"&&(key!=="key"||permitsKey))
      .map(([key,value]) => [key,fieldValue(key,value,permitsKey)]);
    return Object.fromEntries(entries);
  }
  return body;
}

function fieldValue(key: string,value: unknown,permitsKey: boolean): unknown {
  const isCreatedKey=key==="key"&&permitsKey&&typeof value==="string"
    &&/^lgw_[a-z2-7]{12}_[A-Za-z0-9_-]+$/.test(value);
  return isCreatedKey? value:browserResponse(value,false);
}
