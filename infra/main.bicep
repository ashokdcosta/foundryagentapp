@description('Azure region for resources')
param location string = resourceGroup().location

@description('Project name')
param projectName string = 'foundry-agent-app'

@description('Environment')
param environment string = 'dev'

var resourceNamePrefix = '${projectName}-${environment}'

// TODO: Add infrastructure resources
// - App Service Plan
// - App Service
// - Application Insights
// - Log Analytics Workspace
// - Azure AI Foundry Project (if applicable)

output appServiceUrl string = 'https://${resourceNamePrefix}.azurewebsites.net'
