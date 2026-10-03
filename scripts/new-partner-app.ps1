# ──────────────────────────────────────────────────────────────────────────────
#  Create the Partner Center app registration Sybr HUB authenticates as.
#
#  Run it signed in as a Global Administrator of the *partner* tenant:
#
#      pwsh ./scripts/new-partner-app.ps1
#      pwsh ./scripts/new-partner-app.ps1 -WhatIf     # show, change nothing
#
#  What it does, and nothing else: registers one application, adds the two
#  application permissions the client asks for, and issues a client secret.
#  It does not touch a customer tenant, does not create or alter a GDAP
#  relationship, and does not grant admin consent — that last step is a
#  deliberate act and is left to you.
#
#  What it cannot promise: that Partner Center will accept app-only access for
#  these calls. Microsoft has moved that requirement more than once, and the
#  service principal may also need to sit in the AdminAgents group. This script
#  prints exactly what it created so you can check that against Microsoft's
#  current documentation rather than take it on trust. An app that is created
#  cleanly but cannot authenticate is a faster mistake, not a smaller one.
#
#  Requires: PowerShell 7+, Microsoft.Graph.Applications
# ──────────────────────────────────────────────────────────────────────────────
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $DisplayName   = 'Sybr HUB — Partner Center',
    # 24 months is the longest Entra will normally issue. Shorter is safer and
    # means a diary entry; longer is not offered.
    [int]    $SecretMonths  = 12
)

$ErrorActionPreference = 'Stop'

# Resource and permission ids are fixed, published values — not ids from this
# tenant. They are spelled out so the output can be compared against Microsoft's
# documentation without a lookup.
$PARTNER_CENTER_APP_ID = 'fa3d9a0c-3fb0-42cc-9193-47c7ecd2edbd'  # Partner Center API
$PARTNER_CENTER_ROLE   = '1cebfa2a-fb4d-419e-b5f9-839b4383e05a'  # user_impersonation
$GRAPH_APP_ID          = '00000003-0000-0000-c000-000000000000'  # Microsoft Graph
$GRAPH_DIR_READ_ALL    = '7ab1d382-f21e-4acd-a863-ba3e13f7da61'  # Directory.Read.All

function Write-Step { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Warn { param([string]$Text) Write-Host "    ! $Text" -ForegroundColor Yellow }

# ── Module and sign-in ────────────────────────────────────────────────────────
if (-not (Get-Module -ListAvailable -Name Microsoft.Graph.Applications)) {
    throw "Microsoft.Graph.Applications is not installed. Install-Module Microsoft.Graph -Scope CurrentUser"
}
Import-Module Microsoft.Graph.Applications -ErrorAction Stop

Write-Step 'Signing in to the partner tenant'
# Application.ReadWrite.All is what creating a registration needs. It is
# requested rather than assumed so the consent prompt states the scope.
Connect-MgGraph -Scopes 'Application.ReadWrite.All' -NoWelcome
$ctx = Get-MgContext
if (-not $ctx) { throw 'Sign-in failed.' }

$tenantId = $ctx.TenantId
Write-Host "    tenant:  $tenantId"
Write-Host "    account: $($ctx.Account)"

# ── Refuse to create a second one ─────────────────────────────────────────────
# Running this twice would otherwise leave two apps with the same name and no
# way to tell which secret belongs to which.
Write-Step 'Checking for an existing registration'
$existing = Get-MgApplication -Filter "displayName eq '$DisplayName'" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Warn "An application named '$DisplayName' already exists."
    Write-Host  "      appId:    $($existing[0].AppId)"
    Write-Host  "      objectId: $($existing[0].Id)"
    Write-Host  ''
    Write-Host  'Nothing was changed. Add a secret to that app, or delete it first,' -ForegroundColor Yellow
    Write-Host  'or re-run with -DisplayName to register a separate one.'          -ForegroundColor Yellow
    Disconnect-MgGraph | Out-Null
    exit 0
}

# ── What will happen ──────────────────────────────────────────────────────────
Write-Step 'About to create'
Write-Host "    name:        $DisplayName"
Write-Host "    tenant:      $tenantId"
Write-Host "    permissions: Partner Center API  $PARTNER_CENTER_ROLE"
Write-Host "                 Microsoft Graph     $GRAPH_DIR_READ_ALL (Directory.Read.All)"
Write-Host "    secret:      valid $SecretMonths months"
Write-Host ''
Write-Host 'No customer tenant is touched. No GDAP relationship is created or changed.'
Write-Host 'Admin consent is NOT granted — the URL is printed at the end.'

if (-not $PSCmdlet.ShouldProcess($DisplayName, 'Create application registration')) {
    Write-Warn 'WhatIf: stopping here, nothing was created.'
    Disconnect-MgGraph | Out-Null
    exit 0
}

# ── Create ────────────────────────────────────────────────────────────────────
Write-Step 'Registering the application'
$requiredAccess = @(
    @{
        ResourceAppId  = $PARTNER_CENTER_APP_ID
        ResourceAccess = @(@{ Id = $PARTNER_CENTER_ROLE; Type = 'Scope' })
    },
    @{
        ResourceAppId  = $GRAPH_APP_ID
        ResourceAccess = @(@{ Id = $GRAPH_DIR_READ_ALL; Type = 'Role' })
    }
)

$app = New-MgApplication -DisplayName $DisplayName `
                         -SignInAudience 'AzureADMyOrg' `
                         -RequiredResourceAccess $requiredAccess

# A service principal is what consent and group membership attach to. The app
# object alone cannot be consented, and AdminAgents membership — if Partner
# Center still requires it — is granted to this, not to the registration.
$sp = New-MgServicePrincipal -AppId $app.AppId

Write-Step 'Issuing a client secret'
$secret = Add-MgApplicationPassword -ApplicationId $app.Id -PasswordCredential @{
    DisplayName = 'Sybr HUB'
    EndDateTime = (Get-Date).AddMonths($SecretMonths)
}

# ── Report ────────────────────────────────────────────────────────────────────
Write-Step 'Created'
Write-Host ''
Write-Host '  Paste these three into the GDAP / Partner Center card:' -ForegroundColor Green
Write-Host ''
Write-Host "    Partner Tenant ID  $tenantId"
Write-Host "    Client ID          $($app.AppId)"
Write-Host "    Client Secret      $($secret.SecretText)"
Write-Host ''
Write-Warn 'The secret is shown once and cannot be read again. Store it now.'
Write-Host ''
Write-Host "  service principal object id: $($sp.Id)"
Write-Host "  application object id:       $($app.Id)"
Write-Host "  secret expires:              $($secret.EndDateTime)"
Write-Host ''
Write-Host '  Admin consent (not yet granted):' -ForegroundColor Yellow
Write-Host "    https://login.microsoftonline.com/$tenantId/adminconsent?client_id=$($app.AppId)"
Write-Host ''
Write-Host '  Verify before relying on it:' -ForegroundColor Yellow
Write-Host '    - that Partner Center accepts app-only access for these calls;'
Write-Host '    - whether this service principal must be added to AdminAgents.'
Write-Host '    Both have changed in the past and neither is decided by this script.'
Write-Host ''
Write-Host '  To undo everything this created:'
Write-Host "    Remove-MgApplication -ApplicationId $($app.Id)"

Disconnect-MgGraph | Out-Null
