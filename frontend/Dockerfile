FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_EIDOLON_WORK=
ENV NEXT_PUBLIC_EIDOLON_WORK=$NEXT_PUBLIC_EIDOLON_WORK
RUN npm run build
# Private text releases do not ship the old work's decorative character assets.
RUN if [ "$NEXT_PUBLIC_EIDOLON_WORK" = "project-sekai" ]; then \
      rm -rf public/gifts public/reset-card public/sc-opengraph.jpg; \
    fi

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
