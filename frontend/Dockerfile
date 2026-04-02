FROM node:20-alpine

WORKDIR /app

COPY package.json ./package.json
COPY yarn.lock* ./

RUN corepack enable && \
    if [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile --non-interactive; \
    else \
      yarn install --non-interactive; \
    fi && \
    yarn cache clean --all

COPY . .

EXPOSE 3000

CMD ["yarn", "start"]
