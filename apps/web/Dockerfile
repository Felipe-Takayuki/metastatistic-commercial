FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
# um worker basta para estáticos + proxy (o padrão "auto" cria um por núcleo do host: ~5 MB cada, sem ganho aqui)
RUN sed -i -E 's/^worker_processes[[:space:]]+auto;/worker_processes 1;/' /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
