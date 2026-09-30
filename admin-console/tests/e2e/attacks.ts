import { request } from "node:http";

export function abusiveLogin(index: number): Promise<{ status: number; error: string }> {
  const body = JSON.stringify({ key: "lgwa_aaaaaaaaaaaa_" + "A".repeat(43) });
  return new Promise((resolve, reject) => {
    // A distinct real loopback client. Forged headers must not change this socket IP.
    const call = request(
      {
        hostname: "127.0.0.1",
        port: Number(process.env.CONSOLE_TEST_PORT ?? "3100"),
        localAddress: "127.0.0.1",
        path: "/api/auth/login",
        method: "POST",
        headers: {
          Origin: `http://[::1]:${process.env.CONSOLE_TEST_PORT ?? "3100"}`,
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
          "X-Forwarded-For": `198.51.100.${index + 1}`,
          "x-console-client-address": `192.0.2.${index + 1}`,
        },
      },
      (response) => {
        let text = "";
        response.setEncoding("utf8");
        response.on("data", (part) => {
          text += part;
        });
        response.on("end", () =>
          resolve({ status: response.statusCode!, error: JSON.parse(text).error }),
        );
      },
    );
    call.on("error", reject);
    call.end(body);
  });
}
