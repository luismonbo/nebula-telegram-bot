# One-time setup: creates a user-assigned managed identity, grants it "Website
# Contributor" on the target Function App, and adds a federated credential that
# trusts GitHub Actions runs from this repo's main branch. Run manually, once,
# after replacing the placeholders below and running `az login`.
#
# After running, copy the printed clientId/tenantId plus your subscription ID
# (az account show) into GitHub repo secrets: AZURE_CLIENT_ID, AZURE_TENANT_ID,
# AZURE_SUBSCRIPTION_ID. See docs/superpowers/specs/2026-08-09-github-actions-cicd-design.md.

$IdentityName = "nebula-github-deploy"
$ResourceGroup = "telegram-bot-dev"
$FunctionAppName = "nebula-telegram-bot"
$GitHubOrg = "luismonbo"
$GitHubRepo = "nebula-telegram-bot"
$Branch = "main"
$Location = "westeurope"

az identity create --name $IdentityName --resource-group $ResourceGroup --location $Location `
    --query "{clientId: clientId, tenantId: tenantId}" -o table
if ($LASTEXITCODE -ne 0) { throw "az identity create failed" }

$IdentityPrincipal = az identity show --name $IdentityName --resource-group $ResourceGroup --query 'principalId' -o tsv
$FunctionAppId = az functionapp show --name $FunctionAppName --resource-group $ResourceGroup --query 'id' -o tsv

# Newly created identities can take a few seconds to replicate through Entra ID;
# az role assignment create fails with "PrincipalNotFound" if it runs too soon.
$MaxAttempts = 5
$RoleAssigned = $false
for ($Attempt = 1; $Attempt -le $MaxAttempts; $Attempt++) {
    az role assignment create --assignee-object-id $IdentityPrincipal --assignee-principal-type ServicePrincipal `
        --role "Website Contributor" --scope $FunctionAppId
    if ($LASTEXITCODE -eq 0) { $RoleAssigned = $true; break }
    Write-Host "Role assignment failed (attempt $Attempt/$MaxAttempts) - this is normal replication lag for a brand-new identity, retrying in 10s..."
    Start-Sleep -Seconds 10
}
if (-not $RoleAssigned) { throw "az role assignment create failed after $MaxAttempts attempts" }

az identity federated-credential create `
    --identity-name $IdentityName `
    --resource-group $ResourceGroup `
    --name "github-deploy-credential" `
    --issuer "https://token.actions.githubusercontent.com" `
    --subject "repo:${GitHubOrg}/${GitHubRepo}:ref:refs/heads/${Branch}" `
    --audiences "api://AzureADTokenExchange"
if ($LASTEXITCODE -ne 0) { throw "az identity federated-credential create failed" }

Write-Host ""
Write-Host "Done. Add these as GitHub repo secrets (Settings > Secrets and variables > Actions):"
Write-Host "  AZURE_CLIENT_ID       <clientId from above>"
Write-Host "  AZURE_TENANT_ID       <tenantId from above>"
Write-Host "  AZURE_SUBSCRIPTION_ID <run: az account show --query id -o tsv>"
