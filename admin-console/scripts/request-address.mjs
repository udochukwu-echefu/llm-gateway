import { channel } from "node:diagnostics_channel";
import { readConfig } from "../lib/config-schema.mjs";
import { clientAddress, CLIENT_ADDRESS_HEADER } from "./client-address.mjs";

const { ADMIN_CONSOLE_TRUSTED_PROXY_HOPS: hops } = readConfig();
// Node 24 publishes this before emitting the server's request event. Always
// overwrite incoming values, so only the socket or configured proxy chain counts.
channel("http.server.request.start").subscribe(({ request, socket }) => {
  request.headers[CLIENT_ADDRESS_HEADER] = clientAddress(
    socket.remoteAddress, request.headers["x-forwarded-for"], hops,
  );
});
