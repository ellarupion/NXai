# Прод-образ: собирает статику (Vite инлайнит VITE_* переменные в бандл на этапе
# сборки, не читает их в рантайме — поэтому они здесь ARG, а не переменные окружения
# контейнера) и отдаёт её nginx'ом. В отличие от NX, nginx.conf сюда НЕ копируется —
# он смонтирован volume'ом в docker-compose.prod.yml, чтобы правки бэкенд-роутинга
# не требовали пересборки фронтенда.
#
# Build context — КОРЕНЬ репозитория (не web/): `docker build -f web/Dockerfile .`
# (см. docker-compose.prod.yml).

FROM node:22-alpine AS build
WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ .

ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
