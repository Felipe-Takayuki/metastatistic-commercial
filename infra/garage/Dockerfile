# Garage com a configuração embutida (garage.toml). Usado por docker-compose.portainer.yml, que não pode montar arquivos
# do host (o Portainer pode rodar o stack num Docker remoto). Os segredos continuam vindo do ambiente.
FROM dxflrs/garage:v1.0.1
COPY garage.toml /etc/garage.toml
