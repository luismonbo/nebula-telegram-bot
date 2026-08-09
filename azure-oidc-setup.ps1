# One-time setup: creates a user-assigned managed identity, grants it "Website
# Contributor" on the target Function App, and adds a federated credential that
# trusts GitHub Actions runs from this repo's main branch. Run manually, once,
# after replacing the placeholders below and running `az login`.
#
# After running, copy the printed clientId/tenantId plus your subscription ID
# (az account show) into GitHub repo secrets: AZURE_CLIENT_ID, AZURE_TENANT_ID,
# AZURE_SUBSCRIPTION_ID. See docs/superpowers/specs/2026-08-09-github-actions-cicd-design.md.

$IdentityName = "nebula-github-deploy"
$ResourceGroup = "<RESOURCE_GROUP>"
$FunctionAppName = "<FUNCTION_APP_NAME>"
$GitHubOrg = "<GITHUB_ORG>"
$GitHubRepo = "<REPO_NAME>"
$Branch = "main"

az identity create --name $IdentityName --resource-group $ResourceGroup `
    --query "{clientId: clientId, tenantId: tenantId}" -o table

$IdentityPrincipal = az identity show --name $IdentityName --resource-group $ResourceGroup --query 'principalId' -o tsv
$FunctionAppId = az functionapp show --name $FunctionAppName --resource-group $ResourceGroup --query 'id' -o tsv

az role assignment create --assignee $IdentityPrincipal --role "Website Contributor" --scope $FunctionAppId

az identity federated-credential create `
    --identity-name $IdentityName `
    --resource-group $ResourceGroup `
    --name "github-deploy-credential" `
    --issuer "https://token.actions.githubusercontent.com" `
    --subject "repo:${GitHubOrg}/${GitHubRepo}:ref:refs/heads/${Branch}" `
    --audiences "api://AzureADTokenExchange"

Write-Host ""
Write-Host "Done. Add these as GitHub repo secrets (Settings > Secrets and variables > Actions):"
Write-Host "  AZURE_CLIENT_ID       <clientId from above>"
Write-Host "  AZURE_TENANT_ID       <tenantId from above>"
Write-Host "  AZURE_SUBSCRIPTION_ID <run: az account show --query id -o tsv>"
