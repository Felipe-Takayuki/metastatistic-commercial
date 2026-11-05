#!/usr/bin/env bash
# Clona e instala os módulos JASP (com dependências CRAN) em tempo de build, na ordem das dependências entre eles:
#   jaspTTests -> jaspDescriptives -> jaspAnova -> jaspRegression      jaspFrequencies (independente)
# Pacotes R que só existem no GitHub (bstats, conting, flexplot — conferido: são os únicos fora do CRAN/PPM) entram antes, por clone + instalação local
# (nada de remotes::install_github: ele consulta a API do GitHub, limite de 60 req/h sem token).
set -euo pipefail
mkdir -p "$JASP_MODULES_DIR" /opt/r-extra
export R_LIBS_USER=""

strip_remotes() {  # remove "Remotes:" do DESCRIPTION para o remotes não chamar a API do GitHub
  sed -i '/^Remotes:/,/^[A-Za-z]*:/{/^Remotes:/d;/^[[:space:]]/d}' "$1/DESCRIPTION"
}
install_dir() {    # $1 = diretório, $2 = nome do pacote
  Rscript -e "options(Ncpus=4); remotes::install_local('$1', dependencies=TRUE, upgrade='never', force=TRUE); stopifnot(requireNamespace('$2', quietly=TRUE))"
}

# --- pacotes R só do GitHub ---
git clone --depth 1 https://github.com/AlexanderLyNL/bstats.git /opt/r-extra/bstats && strip_remotes /opt/r-extra/bstats && install_dir /opt/r-extra/bstats bstats
git clone --depth 1 https://github.com/vandenman/conting.git    /opt/r-extra/conting && strip_remotes /opt/r-extra/conting && install_dir /opt/r-extra/conting conting
git clone --depth 1 https://github.com/dustinfife/flexplot.git  /opt/r-extra/flexplot && strip_remotes /opt/r-extra/flexplot && install_dir /opt/r-extra/flexplot flexplot

# --- módulos JASP (ordem importa) ---
cd "$JASP_MODULES_DIR"
for mod in jaspTTests jaspDescriptives jaspAnova jaspRegression jaspFrequencies; do
  echo "##### módulo $mod"
  git clone --depth 1 "https://github.com/jasp-stats/$mod.git"
  strip_remotes "$JASP_MODULES_DIR/$mod"
  install_dir "$JASP_MODULES_DIR/$mod" "$mod"
done
