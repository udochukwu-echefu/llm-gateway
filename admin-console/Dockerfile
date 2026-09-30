FROM node:24.15.0-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24.15.0-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
# Only build-time placeholders; runtime configuration is validated by instrumentation.
RUN ADMIN_API_URL=http://gateway-console:8081 ADMIN_CONSOLE_ORIGIN=http://localhost:3100 ADMIN_CONSOLE_SESSION_SECRET=obviously-fake-build-only-secret-at-least-32-bytes npm run build

FROM node:24.15.0-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S -g 1001 console && adduser -S -u 1001 -G console console
COPY --from=builder --chown=console:console /app/.next/standalone ./
COPY --from=builder --chown=console:console /app/.next/static ./.next/static
USER console
EXPOSE 3000
CMD ["node", "server.js"]
