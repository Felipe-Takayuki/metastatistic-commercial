# Instala jaspGraphs -> jaspBase -> jaspSyntax -> jaspTools a partir de clones git.
# Não usa remotes::install_github: ele consulta a API do GitHub (limite de 60 req/h sem token).
options(Ncpus = max(1L, parallel::detectCores() - 1L))
install.packages(c("remotes", "plumber", "jsonlite"))

src <- "/opt/jasp-src"
dir.create(src, showWarnings = FALSE, recursive = TRUE)

install_from_git <- function(repo) {
  path <- file.path(src, repo)
  status <- system2("git", c("clone", "--depth", "1", sprintf("https://github.com/jasp-stats/%s.git", repo), path))
  stopifnot(status == 0)
  # remove "Remotes:" (campo possivelmente multilinha) para o remotes não chamar a API
  desc <- readLines(file.path(path, "DESCRIPTION"))
  start <- grep("^Remotes:", desc)
  if (length(start)) {
    end <- start
    while (end < length(desc) && grepl("^\\s", desc[end + 1])) end <- end + 1
    desc <- desc[-(start:end)]
    writeLines(desc, file.path(path, "DESCRIPTION"))
  }
  remotes::install_local(path, dependencies = TRUE, upgrade = "never", force = TRUE)
}

for (repo in c("jaspGraphs", "jaspBase", "jaspSyntax", "jaspTools")) install_from_git(repo)
stopifnot(requireNamespace("jaspTools", quietly = TRUE))
