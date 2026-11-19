# ──────────────────────────────────────────────────────────────────────────────
#  Create the Partner Center app registration Sybr HUB authenticates as.
#
#  Run it signed in as a Global Administrator of the *partner* tenant:
#
#      pwsh ./scripts/new-partner-app.ps1
#      pwsh ./scripts/new-partner-app.ps1 -WhatIf     # show, change nothing
#
#  What it does, and nothing else: registers one *multi-tenant* application,
#  adds read-only application permissions, and issues a client secret. It does
#  not touch a customer tenant, does not create or alter a GDAP relationship,
#  and does not grant admin consent — that is a deliberate act and is left to
#  you, once in the partner tenant and once in each customer tenant.
#
#  Why multi-tenant. GDAP gives roles to *users* in security groups; it does
#  not let an application read a customer tenant. Sybr HUB reads customer
#  tenants app-only (client credentials), so the same app must exist in each
#  customer tenant as a service principal with admin consent. Multi-tenant is
#  what lets one registration be consented into many tenants. The hub shows a
#  consent link per customer on the GDAP card.
#
#  Read-only, on purpose. Every permission below ends in .Read.All or reads.
#  One secret that could write to every customer's tenant is the worst thing
#  this hub could leak. Writes (Conditional Access deployment) stay on the
#  per-customer path, granted per customer.
#
#  The hub reads the GDAP customer list from Microsoft Graph, so the app does
#  not need to be registered under Partner Center → App management.
#
#  Requires: PowerShell 7+, Microsoft.Graph.Applications
# ──────────────────────────────────────────────────────────────────────────────
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $DisplayName   = 'Sybr HUB — Partner Center',
    # 24 months is the longest Entra will normally issue. Shorter is safer and
    # means a diary entry; longer is not offered.
    [int]    $SecretMonths  = 12,
    # Where Entra sends the admin after a consent click, e.g. the hub's own
    # URL. Optional: without it the consent is still recorded, the browser
    # just ends on an error page instead of somewhere friendly.
    [string] $RedirectUri   = ''
)

$ErrorActionPreference = 'Stop'

# Resource and permission ids are fixed, published values — not ids from this
# tenant. They are spelled out so the output can be compared against Microsoft's
# documentation without a lookup.
$PARTNER_CENTER_APP_ID = 'fa3d9a0c-3fb0-42cc-9193-47c7ecd2edbd'  # Partner Center API
$PARTNER_CENTER_ROLE   = '1cebfa2a-fb4d-419e-b5f9-839b4383e05a'  # user_impersonation
$GRAPH_APP_ID          = '00000003-0000-0000-c000-000000000000'  # Microsoft Graph

# Application permissions on Microsoft Graph, by name. The ids are looked up
# from the Graph service principal at run time rather than copied in, so a
# typo fails loudly here instead of producing an app with a silent gap.
#
# Keep in step with REQUIRED_GRAPH_PERMISSIONS in app/core/config.py plus
# DelegatedAdminRelationship.Read.All (listing GDAP relationships). A test
# (tests/test_partner_app_script.py) fails if they drift. Nothing here may
# write: the same test refuses any name containing "ReadWrite".
$GRAPH_PERMISSIONS = @(
    # BEGIN GRAPH PERMISSIONS
    'AuditLog.Read.All'
    'Application.Read.All'
    'DeviceManagementApps.Read.All'
    'DeviceManagementConfiguration.Read.All'
    'DeviceManagementManagedDevices.Read.All'
    'DeviceManagementServiceConfig.Read.All'
    'Device.Read.All'
    'Directory.Read.All'
    'Group.Read.All'
    'IdentityRiskyUser.Read.All'
    'IdentityRiskEvent.Read.All'
    'Organization.Read.All'
    'Policy.Read.All'
    'Reports.Read.All'
    'RoleManagement.Read.Directory'
    'SecurityEvents.Read.All'
    'Sites.Read.All'
    'SharePointTenantSettings.Read.All'
    'User.Read.All'
    'UserAuthenticationMethod.Read.All'
    'AccessReview.Read.All'
    'SecurityAlert.Read.All'
    'SecurityIncident.Read.All'
    'SensitivityLabels.Read.All'
    'BackupRestore-Control.Read.All'
    'BackupRestore-Configuration.Read.All'
    'DelegatedAdminRelationship.Read.All'
    # END GRAPH PERMISSIONS
)

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

# ── Resolve permission ids ───────────────────────────────────────────────────
Write-Step 'Resolving Microsoft Graph permission ids'
$graphSp = Get-MgServicePrincipal -Filter "appId eq '$GRAPH_APP_ID'" -ErrorAction Stop
$graphRoles = @()
foreach ($name in $GRAPH_PERMISSIONS) {
    $role = $graphSp.AppRoles | Where-Object { $_.Value -eq $name -and $_.AllowedMemberTypes -contains 'Application' }
    if (-not $role) { throw "Microsoft Graph has no application permission named '$name'." }
    $graphRoles += @{ Id = $role.Id; Type = 'Role' }
}
Write-Host "    $($graphRoles.Count) read-only permissions resolved"

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
Write-Host "    audience:    multi-tenant (AzureADMultipleOrgs)"
Write-Host "    permissions: Partner Center API  $PARTNER_CENTER_ROLE"
Write-Host "                 Microsoft Graph     $($GRAPH_PERMISSIONS.Count) read-only application permissions"
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
        ResourceAccess = $graphRoles
    }
)

$appParams = @{
    DisplayName            = $DisplayName
    SignInAudience         = 'AzureADMultipleOrgs'
    RequiredResourceAccess = $requiredAccess
}
if ($RedirectUri) { $appParams.Web = @{ RedirectUris = @($RedirectUri) } }
$app = New-MgApplication @appParams

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
Write-Host '  Next steps (none of them done by this script):' -ForegroundColor Yellow
Write-Host '    1. Admin consent in the partner tenant:'
Write-Host "       https://login.microsoftonline.com/$tenantId/adminconsent?client_id=$($app.AppId)"
Write-Host '    2. Paste the three values above into the GDAP card in Sybr HUB. The'
Write-Host '       customer list is read from Graph; Partner Center App management is'
Write-Host '       only needed for the Partner Center API, which the hub does not use.'
Write-Host '    3. Per customer: open the consent link on the GDAP card in Sybr HUB and'
Write-Host '       sign in as an admin of that customer (Global Admin or'
Write-Host '       Privileged Role Administrator). Until then audits of that'
Write-Host '       customer fail with "app not found in directory".'
Write-Host ''
Write-Host '  To undo everything this created:'
Write-Host "    Remove-MgApplication -ApplicationId $($app.Id)"

Disconnect-MgGraph | Out-Null
