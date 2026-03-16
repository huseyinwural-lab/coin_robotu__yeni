FROM node:20-alpine

WORKDIR /app

COPY . .

RUN corepack enable && \
    if [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile --non-interactive; \
    else \
      yarn install --non-interactive; \
    fi

EXPOSE 3000

CMD ["yarn", "start"]
