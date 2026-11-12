import os
import tempfile

# Os serviços leem a configuração ao serem importados: define os bancos ANTES de importar platform_service.
_TMP = tempfile.mkdtemp(prefix="platform-test-")
for name in ("AUDIT", "AUTH", "BILLING", "BI"):
    os.environ[f"{name}_DATABASE_URL"] = f"sqlite:///{_TMP}/{name.lower()}.db"
os.environ["AUDIT_SERVICE_URL"] = ""      # auth-tenant não tenta enviar eventos a um servidor que não existe no teste
os.environ["TEMP_DIR"] = f"{_TMP}/export"
os.environ["STRIPE_MOCK_MODE"] = "true"
