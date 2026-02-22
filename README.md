# Foundry Agent Service

A full-stack Python application for Microsoft Foundry Agent Service with FastAPI backend and React frontend.

## Project Structure

```
.
├── src/
│   ├── api/              # FastAPI backend
│   ├── web/              # React frontend
│   ├── agents/           # Agent creation and management
│   └── tests/            # Smoke tests
├── infra/                # Infrastructure as Code (Bicep)
├── .env.example          # Environment variables template
├── requirements.txt      # Python dependencies
└── azure.yaml            # Azure Developer CLI (azd) configuration
```

## Setup & Configuration

### Environment Variables

1. Copy the example configuration:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set your values:
   ```
   PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
   StoreOps_MODEL_DEPLOYMENT=<your-model-deployment>
   Inventory_MODEL_DEPLOYMENT=<your-model-deployment>
   Planogram_MODEL_DEPLOYMENT=<your-model-deployment>
   ```

Replace `<resource>`, `<project>`, and deployment names with your actual Azure Foundry values.

**Model Deployments:**
- `StoreOps_MODEL_DEPLOYMENT` — Model for StoreOpsAgent
- `Inventory_MODEL_DEPLOYMENT` — Model for InventoryAgent
- `Planogram_MODEL_DEPLOYMENT` — Model for PlanogramAgent

**Note:** Never commit `.env` to version control. Use `.env` for local development only.

### Authentication

The application uses **DefaultAzureCredential** which automatically handles authentication in the following order:

1. **Local Development** (Azure CLI)
   ```bash
   az login
   ```
   Sign in with your Azure account. The SDK will use your CLI credentials.

2. **Environment Variables**
   Set `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, and `AZURE_TENANT_ID` for service principal authentication.

3. **ManagedLocally

#### Backend (FastAPI)
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python -m uvicorn src.api.main:app --reload
```Deployment

Use Azure Developer CLI (azd) for automated deployment:

```bash
# Initialize or link to existing Azure resources
azd auth login
azd up
```

This will provision infrastructure defined in `infra/main.bicep` and deploy both backend and frontend.

### Security Notes

- **Never commit secrets** to the repository
- `.env` is in `.gitignore` — add sensitive data there only
- Use Azure CLI (`az login`) or managed identity for authentication
- Store secrets in Azure Key Vault for produc
cd src/web
npm install
npm run dev
```
Frontend available at `http://localhost:5173` or `http://localhost:3000`

#### Tests
```bash
pytest src/tests/he Application

```bash
python app.py
```

### Security Notes

- **Never commit secrets** to the repository
- Use environment variables or Azure Key Vault for configuration
- Store credentials in `.env` (add to `.gitignore`) or use Azure CLI authentication
- Rotate credentials regularly
