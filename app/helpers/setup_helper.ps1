# MSP Toolkit — First-run setup via Microsoft Graph
#
# Uses Microsoft.Graph.Authentication for reliable delegated auth + admin-consent.
# Azure ARM role assignment still uses a separate raw device-code token.
#
# Input  : JSON on stdin   { cert_der_b64, cert_expiry, cert_start, app_name,
#                            required_permissions[] }
# Output : structured lines on stdout
#   [STEP] <message>
#   [DEVICE_CODE_1] url=<url> code=<code>     <- Graph / M365 auth
#   [DEVICE_CODE_2] url=<url> code=<code>     <- Azure ARM auth
#   [RESULT] <compact-json>
#   [ERROR] <message>

param()
$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
$PSStyle.OutputRendering = 'PlainText'

function out-step   { param($m) [Console]::WriteLine("[STEP] $m") }
function out-result { param($o) [Console]::WriteLine("[RESULT] $($o | ConvertTo-Json -Compress -Depth 10)") }
function out-err    { param($m) [Console]::WriteLine("[ERROR] $m"); exit 1 }

# ── Read input JSON from stdin ────────────────────────────────────────────────
try {
    $inp        = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $certDerB64 = $inp.cert_der_b64
    $certExpiry = $inp.cert_expiry
    $certStart  = $inp.cert_start
    $appName    = if ($inp.app_name) { $inp.app_name } else { 'MSP Toolkit Audit' }
    # Handed in by the caller so this file is not a third copy of the list.
    $permsIn    = $inp.required_permissions
} catch {
    out-err "Failed to read input: $_"
}

# ── Ensure Microsoft.Graph.Authentication module ──────────────────────────────
out-step "Checking Microsoft.Graph.Authentication module..."
$mgMod = Get-Module -ListAvailable -Name Microsoft.Graph.Authentication -ErrorAction SilentlyContinue |
         Sort-Object Version -Descending | Select-Object -First 1
if (-not $mgMod) {
    out-step "Installing Microsoft.Graph.Authentication (first-time, ~50 MB)..."
    try {
        # Ensure NuGet provider present
        if (-not (Get-PackageProvider -Name NuGet -ErrorAction SilentlyContinue)) {
            Install-PackageProvider -Name NuGet -Force -Scope CurrentUser | Out-Null
        }
        Install-Module Microsoft.Graph.Authentication `
            -Scope CurrentUser -Force -AllowClobber -Repository PSGallery -ErrorAction Stop
        out-step "Module installed."
    } catch {
        out-err "Could not install Microsoft.Graph.Authentication: $_"
    }
}
Import-Module Microsoft.Graph.Authentication -Force -ErrorAction Stop

# ── Force completely fresh Graph login ──
try { Disconnect-MgGraph -ErrorAction SilentlyContinue } catch {}
try { [Microsoft.Graph.PowerShell.Authentication.GraphSession]::Instance.AuthContext = $null } catch {}

# ── Graph authentication ──────────────────────────────────────────────────────
out-step "Starting Microsoft 365 authentication (device code)..."

$graphScopes = @(
    'Application.ReadWrite.All'
    'AppRoleAssignment.ReadWrite.All'
    'RoleManagement.ReadWrite.Directory'
    'Directory.ReadWrite.All'
    'Organization.Read.All'
)

# Obtain a device-code token manually via raw OAuth2 — this bypasses MSAL
# cache entirely and guarantees a fresh login every time.
$GRAPH_PS_CLIENT = '14d82eec-204b-4c2f-b7e8-296a70dab67e'
$scopeStr = ($graphScopes | ForEach-Object { "https://graph.microsoft.com/$_" }) -join ' '
$scopeStr += ' offline_access openid profile'

$dcResp = Invoke-RestMethod -Method POST `
    -Uri "https://login.microsoftonline.com/organizations/oauth2/v2.0/devicecode" `
    -Body @{ client_id = $GRAPH_PS_CLIENT; scope = $scopeStr } `
    -ContentType 'application/x-www-form-urlencoded'

[Console]::WriteLine("[DEVICE_CODE_1] url=$($dcResp.verification_uri) code=$($dcResp.user_code)")

# Poll for token
$interval = [int]($dcResp.interval ?? 5)
$deadline = (Get-Date).AddSeconds([int]$dcResp.expires_in)
$graphToken = $null

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $interval
    try {
        $t = Invoke-RestMethod -Method POST `
            -Uri "https://login.microsoftonline.com/organizations/oauth2/v2.0/token" `
            -Body @{
                client_id   = $GRAPH_PS_CLIENT
                device_code = $dcResp.device_code
                grant_type  = 'urn:ietf:params:oauth:grant-type:device_code'
            } `
            -ContentType 'application/x-www-form-urlencoded' `
            -ErrorAction Stop
        $graphToken = $t.access_token
        break
    } catch {
        $err = $null
        try { $err = ($_.ErrorDetails.Message | ConvertFrom-Json).error } catch {}
        if ($err -eq 'authorization_pending') { continue }
        if ($err -eq 'slow_down') { $interval += 5; continue }
        out-err "Graph authentication failed: $($_.ErrorDetails.Message)"
    }
}

if (-not $graphToken) {
    out-err "Graph authentication timed out — no token received."
}

# Connect Microsoft.Graph module using the token we obtained
Connect-MgGraph -AccessToken (ConvertTo-SecureString $graphToken -AsPlainText -Force) -NoWelcome

$ctx = Get-MgContext
if (-not $ctx) {
    out-err "Graph authentication failed — no active context."
}
out-step "Graph authentication successful. (TenantId: $($ctx.TenantId))"

# ── Graph REST helpers (Invoke-MgGraphRequest — token managed by the module) ──
function gget {
    param($path, $query = '')
    $uri = "https://graph.microsoft.com/v1.0/$path"
    if ($query) { $uri += "?$query" }
    Invoke-MgGraphRequest -Method GET -Uri $uri -OutputType PSObject
}

function gpost {
    param($path, $body)
    Invoke-MgGraphRequest -Method POST `
        -Uri "https://graph.microsoft.com/v1.0/$path" `
        -Body ($body | ConvertTo-Json -Depth 10) `
        -ContentType 'application/json' `
        -OutputType PSObject
}

function gpatch {
    param($path, $body)
    Invoke-MgGraphRequest -Method PATCH `
        -Uri "https://graph.microsoft.com/v1.0/$path" `
        -Body ($body | ConvertTo-Json -Depth 10) `
        -ContentType 'application/json' | Out-Null
}

function gsafepost {
    param($path, $body)
    try { gpost $path $body | Out-Null }
    catch { if ($_.ToString() -notmatch 'already exists') { Write-Warning "Non-fatal: $_" } }
}

# ── Tenant info ───────────────────────────────────────────────────────────────
out-step "Fetching tenant information..."
$org        = (gget 'organization').value[0]
$tenantId   = $org.id
$custName   = $org.displayName
$primDomain = ($org.verifiedDomains | Where-Object { $_.isDefault } | Select-Object -First 1).name
$initDomain = ($org.verifiedDomains | Where-Object { $_.isInitial } | Select-Object -First 1).name
out-step "Tenant: $custName ($primDomain)"

# ── App registration ──────────────────────────────────────────────────────────
out-step "Creating app registration '$appName'..."
$existing = (gget 'applications' "`$filter=displayName eq '$appName'&`$top=1").value
if ($existing.Count -gt 0) {
    $app = $existing[0]
    out-step "Reusing existing app: $($app.appId)"
} else {
    $app = gpost 'applications' @{ displayName = $appName; signInAudience = 'AzureADMyOrg' }
    out-step "App created: $($app.appId)"
}
$appId       = $app.appId
$appObjectId = $app.id

# ── API permissions ───────────────────────────────────────────────────────────
out-step "Configuring API permissions..."
$graphResourceId = '00000003-0000-0000-c000-000000000000'
$exoResourceId   = '00000002-0000-0ff1-ce00-000000000000'

$graphSP    = (gget 'servicePrincipals' "`$filter=appId eq '$graphResourceId'").value[0]
$graphRoles = @{}
$graphSP.appRoles |
    Where-Object { $_.allowedMemberTypes -contains 'Application' } |
    ForEach-Object { $graphRoles[$_.value] = $_.id }

$fallbackPerms = @(
    'AuditLog.Read.All','Application.Read.All',
    'DeviceManagementApps.Read.All','DeviceManagementConfiguration.Read.All',
    'DeviceManagementManagedDevices.Read.All','DeviceManagementServiceConfig.Read.All',
    'Device.Read.All','Directory.Read.All','Group.Read.All',
    'IdentityRiskyUser.Read.All',
    'Organization.Read.All','Policy.Read.All','RoleManagement.Read.Directory',
    'SecurityEvents.Read.All','Sites.Read.All','SharePointTenantSettings.Read.All',
    'User.Read.All','UserAuthenticationMethod.Read.All',
    'InformationProtectionPolicy.Read.All','AccessReview.Read.All','SecurityAlert.Read.All'
)

# The caller passes the list it also validates against; the literal above is
# only reached when an older caller sends nothing, and grants a consent that
# would then not match what GraphClient checks for.
$requiredPerms = if ($permsIn -and $permsIn.Count -gt 0) { @($permsIn) } else {
    out-step 'Advarsel: ingen tillatelsesliste mottatt — bruker innebygd fallback'
    $fallbackPerms
}

$graphAccess = $requiredPerms |
    Where-Object { $graphRoles.ContainsKey($_) } |
    ForEach-Object { @{ id = $graphRoles[$_]; type = 'Role' } }

$exoSpData = (gget 'servicePrincipals' "`$filter=appId eq '$exoResourceId'").value
$exoAccess = @()
$script:exoSpId = $null; $script:exoRoleId = $null
if ($exoSpData.Count -gt 0) {
    $exoRole = $exoSpData[0].appRoles | Where-Object { $_.value -eq 'Exchange.ManageAsApp' }
    if ($exoRole) {
        $exoAccess        = @(@{ id = $exoRole.id; type = 'Role' })
        $script:exoSpId   = $exoSpData[0].id
        $script:exoRoleId = $exoRole.id
    }
}

$resourceAccess = @(@{ resourceAppId = $graphResourceId; resourceAccess = @($graphAccess) })
if ($exoAccess.Count -gt 0) {
    $resourceAccess += @{ resourceAppId = $exoResourceId; resourceAccess = $exoAccess }
}

gpatch "applications/$appObjectId" @{ requiredResourceAccess = $resourceAccess }

# ── Service principal + admin consent ─────────────────────────────────────────
out-step "Creating service principal and granting admin consent..."
$spExisting = (gget 'servicePrincipals' "`$filter=appId eq '$appId'").value
$sp         = if ($spExisting.Count -gt 0) { $spExisting[0] } else { gpost 'servicePrincipals' @{ appId = $appId } }
$spId       = $sp.id
$graphSpId  = $graphSP.id

foreach ($perm in $requiredPerms) {
    if (-not $graphRoles.ContainsKey($perm)) { continue }
    gsafepost "servicePrincipals/$spId/appRoleAssignments" @{
        principalId = $spId; resourceId = $graphSpId; appRoleId = $graphRoles[$perm]
    }
}
if ($script:exoSpId) {
    gsafepost "servicePrincipals/$spId/appRoleAssignments" @{
        principalId = $spId; resourceId = $script:exoSpId; appRoleId = $script:exoRoleId
    }
}

# Exchange Administrator role
try {
    $exRole = (gget 'directoryRoles' "`$filter=displayName eq 'Exchange Administrator'").value
    if ($exRole.Count -eq 0) {
        $tmpl = (gget 'directoryRoleTemplates').value | Where-Object { $_.displayName -eq 'Exchange Administrator' }
        if ($tmpl) { gpost 'directoryRoles' @{ roleTemplateId = $tmpl.id } | Out-Null }
        $exRole = (gget 'directoryRoles' "`$filter=displayName eq 'Exchange Administrator'").value
    }
    if ($exRole.Count -gt 0) {
        gsafepost "directoryRoles/$($exRole[0].id)/members/`$ref" @{
            '@odata.id' = "https://graph.microsoft.com/v1.0/directoryObjects/$spId"
        }
    }
} catch { out-step "Exchange Admin role: non-fatal warning" }

# ── Certificate upload ────────────────────────────────────────────────────────
out-step "Uploading certificate to app registration..."
gpatch "applications/$appObjectId" @{
    keyCredentials = @(@{
        type          = 'AsymmetricX509Cert'
        usage         = 'Verify'
        key           = $certDerB64
        displayName   = "MSPToolkitCert-$(Get-Date -Format 'yyyy-MM-dd')"
        endDateTime   = $certExpiry
        startDateTime = $certStart
    })
}

# ── Client secret ─────────────────────────────────────────────────────────────
out-step "Creating client secret (1 year)..."
$appDetail = gget "applications/$appObjectId" '$select=passwordCredentials'
foreach ($cred in $appDetail.passwordCredentials) {
    try {
        Invoke-MgGraphRequest -Method POST `
            -Uri "https://graph.microsoft.com/v1.0/applications/$appObjectId/removePassword" `
            -Body (@{ keyId = $cred.keyId } | ConvertTo-Json) `
            -ContentType 'application/json' | Out-Null
    } catch {}
}

$secretResult = gpost "applications/$appObjectId/addPassword" @{
    passwordCredential = @{
        displayName = "MSPToolkit-$(Get-Date -Format 'yyyy-MM-dd')"
        endDateTime = (Get-Date).ToUniversalTime().AddDays(365).ToString('o')
    }
}
$clientSecret = $secretResult.secretText
$secretExpiry = if ($secretResult.endDateTime -is [DateTime]) {
    $secretResult.endDateTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
} else {
    "$($secretResult.endDateTime)"
}
out-step "Secret created, expires: $($secretExpiry.Substring(0,10))"

# ── Azure ARM role assignment (separate device-code token) ────────────────────
out-step "Starting Azure authentication for role assignment..."
# Try multiple well-known public clients for ARM access.
# Azure CLI may not be registered in all tenants; Graph PS is more common.
$armClients = @(
    '04b07795-a710-4e09-9a32-185a286bb6ee'   # Azure CLI
    '1950a258-227b-4e31-a9cf-717495945fc2'   # Azure PowerShell
    '14d82eec-204b-4c2f-b7e8-296a70dab67e'   # Microsoft Graph PowerShell
)
$subId = ''
$armToken = $null
try {
    $dcResp = $null
    foreach ($armClient in $armClients) {
        try {
            $dcResp = Invoke-RestMethod -Method POST `
                -Uri "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/devicecode" `
                -Body @{ client_id = $armClient; scope = 'https://management.azure.com/user_impersonation' } `
                -ContentType 'application/x-www-form-urlencoded' `
                -ErrorAction Stop
            break  # success — use this client
        } catch {
            continue  # try next client
        }
    }

    if (-not $dcResp) {
        out-step "No Azure ARM client available in this tenant — skipping role assignment"
    } else {
        [Console]::WriteLine("[DEVICE_CODE_2] url=$($dcResp.verification_uri) code=$($dcResp.user_code)")

        $interval = [int]($dcResp.interval ?? 5)
        $deadline = (Get-Date).AddSeconds([int]$dcResp.expires_in)

        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds $interval
            try {
                $t = Invoke-RestMethod -Method POST `
                    -Uri "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token" `
                    -Body @{
                        client_id   = $armClient
                        device_code = $dcResp.device_code
                        grant_type  = 'urn:ietf:params:oauth:grant-type:device_code'
                    } `
                    -ContentType 'application/x-www-form-urlencoded' `
                    -ErrorAction Stop
                $armToken = $t.access_token
                break
            } catch {
                $err = $null
                try { $err = ($_.ErrorDetails.Message | ConvertFrom-Json).error } catch {}
                if ($err -eq 'authorization_pending') { continue }
                if ($err -eq 'slow_down') { $interval += 5; continue }
                out-step "ARM auth warning: $($_.ErrorDetails.Message)"
                break
            }
        }
    }

    if ($armToken) {
        $armHeaders = @{ Authorization = "Bearer $armToken"; 'Content-Type' = 'application/json' }
        $subs = (Invoke-RestMethod -Uri 'https://management.azure.com/subscriptions?api-version=2022-12-01' -Headers $armHeaders).value

        if ($subs.Count -gt 0) {
            # Use first sub as primary for config, but assign roles on ALL subs
            $subId = $subs[0].subscriptionId
            out-step "Found $($subs.Count) Azure subscription(s)"

            $roles = @(
                @{ name = 'Reader';                 id = 'acdd72a7-3385-48ef-bd42-f606fba81ae7' }
                @{ name = 'Cost Management Reader'; id = '72fafb9e-0641-4937-9268-a91bfd8191a3' }
            )

            foreach ($sub in $subs) {
                $sid = $sub.subscriptionId
                $sname = $sub.displayName
                out-step "Assigning roles on: $sname ($sid)"

                foreach ($role in $roles) {
                    $assignId = [System.Guid]::NewGuid().ToString()
                    $url = "https://management.azure.com/subscriptions/$sid/providers/Microsoft.Authorization/roleAssignments/$($assignId)?api-version=2022-04-01"
                    try {
                        Invoke-RestMethod -Method PUT -Uri $url -Headers $armHeaders -Body (@{
                            properties = @{
                                roleDefinitionId = "/subscriptions/$sid/providers/Microsoft.Authorization/roleDefinitions/$($role.id)"
                                principalId      = $spId
                                principalType    = 'ServicePrincipal'
                            }
                        } | ConvertTo-Json -Depth 5) | Out-Null
                    } catch {
                        $code = $null
                        try { $code = ($_.ErrorDetails.Message | ConvertFrom-Json).error.code } catch {}
                        if ($code -ne 'RoleAssignmentExists') { out-step "Role '$($role.name)' on '$sname': $code" }
                    }
                }
            }
            out-step "Roles assigned on $($subs.Count) subscription(s)"
        } else {
            out-step "No Azure subscriptions found — skipping role assignment"
        }
    } else {
        out-step "ARM auth timed out — skipping Azure role assignment"
    }
} catch {
    out-step "Azure role assignment skipped: $_"
}

# ── Wait for propagation ──────────────────────────────────────────────────────
out-step "Waiting 20 seconds for permissions to propagate..."
Start-Sleep -Seconds 20

# ── Output result ─────────────────────────────────────────────────────────────
out-result @{
    tenant_id       = $tenantId
    client_id       = $appId
    app_object_id   = $appObjectId
    customer_name   = $custName
    primary_domain  = $primDomain
    initial_domain  = $initDomain
    client_secret   = $clientSecret
    secret_expiry   = $secretExpiry
    subscription_id = $subId
}
