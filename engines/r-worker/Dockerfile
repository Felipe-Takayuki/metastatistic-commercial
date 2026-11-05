# Worker estatístico: roda análises do JASP (jaspTools + módulos) em R.
FROM rocker/r-ver:4.6.1 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    JASP_MODULES_DIR=/opt/jasp-modules \
    DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl wget ca-certificates cmake pkg-config \
      libcurl4-openssl-dev libssl-dev libxml2-dev libarchive-dev \
      libopengl0 libglvnd0 libgl1 libegl1 \
      libfontconfig1-dev libfreetype6-dev libharfbuzz-dev libfribidi-dev \
      libpng-dev libjpeg-dev libtiff5-dev libwebp-dev \
      libnlopt-dev libgmp-dev libmpfr-dev libgsl-dev libsodium-dev \
      libglpk-dev libicu-dev libudunits2-dev \
    && rm -rf /var/lib/apt/lists/*

FROM base AS build

# Dependências do worker HTTP + jaspTools (e jaspSyntax, que baixa uma lib nativa)
COPY install-deps.R /tmp/install-deps.R
RUN Rscript /tmp/install-deps.R

# Módulos JASP usados pela plataforma (clonados para module.dirs do jaspTools)
COPY install-modules.sh /tmp/install-modules.sh
RUN bash /tmp/install-modules.sh

# Leitura de Parquet (pequena, sem dependências). Camada separada para não invalidar o cache dos módulos.
# + callr: o supervisor comanda o motor (processo filho) por ele.
RUN Rscript -e 'install.packages(c("nanoparquet", "callr")); stopifnot(requireNamespace("nanoparquet", quietly = TRUE), requireNamespace("callr", quietly = TRUE))'

COPY setup-jasp.R /app/
WORKDIR /app
RUN Rscript /app/setup-jasp.R
# engine.R e runner.R ficam DEPOIS do download do jaspTools: mexer neles não refaz esses minutos.
COPY engine.R runner.R /app/

EXPOSE 8000
CMD ["Rscript", "-e", "plumber::pr_run(plumber::pr('/app/runner.R'), host='0.0.0.0', port=8000)"]
