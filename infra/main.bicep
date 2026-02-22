@description('Azure region for resources')
param location string = resourceGroup().location

@description('Project name')
param projectName string = 'foundry-agent-app'

@description('Environment name (dev, qa, prod)')
param environment string = 'dev'

var prefix = '${projectName}-${environment}'

/*
 * App Service Plan (Linux)
 */
resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${prefix}-plan'
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

/*
 * Log Analytics Workspace
 */
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${prefix}-law'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
  }
}

/*
 * Application Insights
 */
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-appi'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

/*
 * App Service (FastAPI backend)
 */
resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: prefix
  location: location
  kind: 'app,linux'
  tags: {
    'azd-service-name': 'api'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: true

      // Start FastAPI from api.main since project root is src/ (not src/api)
      // This allows imports like 'from agents.foundry_client import ...' to resolve
      appCommandLine: 'python -m uvicorn api.main:app --host 0.0.0.0 --port 8000'

      appSettings: [
        {
          name: 'ENVIRONMENT'
          value: environment
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'ENABLE_ORYX_BUILD'
          value: 'true'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '0'
        }
      ]
    }
    httpsOnly: true
  }
}

/*
 * Outputs
 */
output appServiceName string = webApp.name
output appServiceUrl string = 'https://${webApp.name}.azurewebsites.net'