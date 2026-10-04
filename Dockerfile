FROM python:3.13-slim

WORKDIR /app
COPY . .

# Le paquet (hatchling) tire httpx/pydantic/uvicorn ; on pinne mcp sur la version
# éprouvée (1.28.1) : oauth.py modifie des routes internes du SDK, qu'une autre version peut changer.
RUN pip install --no-cache-dir . 'mcp[cli]==1.28.1'

# Configuration par variables d'environnement : voir .env.example et
# compose.yaml.
CMD ["pennylane-mcp-server"]
