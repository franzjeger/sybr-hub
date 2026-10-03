# ──────────────────────────────────────────────────────────────────────────────
#  EXO Collector — called by Python app via subprocess
#  Reads config JSON from stdin, outputs results as JSON to stdout.
#  Requires: ExchangeOnlineManagement >= 3.0, PowerShell 7+
# ──────────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = 'Continue'
$WarningPreference     = 'SilentlyContinue'

# Read config from stdin
$configJson = $input | Out-String
if (-not $configJson.Trim()) { Write-Output '{"error":"No config received on stdin"}'; exit 1 }

try { $cfg = $configJson | ConvertFrom-Json }
catch { Write-Output "{`"error`":`"Invalid JSON config: $_`"}"; exit 1 }

$tenantId    = $cfg.TenantId
$clientId    = $cfg.ClientId
$certPath    = $cfg.CertPath
$certPwd     = $cfg.CertPassword
$orgDomain   = $cfg.OrgDomain

$result = [ordered]@{ connected = $false }

# ── Load cert from PFX ────────────────────────────────────────────────────────
if (-not (Test-Path $certPath)) {
    Write-Output "{`"error`":`"Certificate not found: $certPath`"}"
    exit 1
}

try {
    $certBytes = [System.IO.File]::ReadAllBytes($certPath)
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        $certBytes, $certPwd,
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable
    )
} catch {
    Write-Output "{`"error`":`"Failed to load certificate: $_`"}"
    exit 1
}

# ── Install module if missing ──────────────────────────────────────────────────
if (-not (Get-Module -ListAvailable -Name ExchangeOnlineManagement | Where-Object { $_.Version -ge '3.0.0' })) {
    try {
        Install-Module ExchangeOnlineManagement -Scope CurrentUser -Force -AllowClobber -ErrorAction Stop
    } catch {
        Write-Output "{`"error`":`"Could not install ExchangeOnlineManagement: $_`"}"
        exit 1
    }
}
Import-Module ExchangeOnlineManagement -MinimumVersion 3.0.0 -ErrorAction Stop

# ── Connect ───────────────────────────────────────────────────────────────────
try {
    Connect-ExchangeOnline -AppId $clientId -Certificate $cert -Organization $orgDomain -ShowBanner:$false -ErrorAction Stop
    $result.connected = $true
} catch {
    Write-Output "{`"error`":`"EXO connection failed: $_`"}"
    exit 1
}

# ── Helper: safe serialize ────────────────────────────────────────────────────
function Safe-Json($obj) {
    try { return ($obj | ConvertTo-Json -Depth 5 -Compress -ErrorAction Stop) }
    catch { return '[]' }
}

# ── Mailboxes (all types: User, Shared, Room, Equipment) ─────────────────────
try {
    $mbx = @()
    foreach ($rType in @('UserMailbox', 'SharedMailbox', 'RoomMailbox', 'EquipmentMailbox')) {
        # A tenant with no room or equipment mailboxes makes Get-Mailbox return
        # $null, and "+= $null" appends a null *element* rather than nothing.
        # That null then reached Get-MailboxStatistics, which threw "Cannot bind
        # argument to parameter 'Identity' because it is null" — and the catch
        # below discarded every mailbox already collected. One absent recipient
        # type silently cost the whole mailbox inventory.
        $found = Get-Mailbox -RecipientTypeDetails $rType -ResultSize Unlimited -ErrorAction SilentlyContinue
        if ($found) { $mbx += $found }
    }
    $mbxData = $mbx | Where-Object { $_ -and $_.Identity } | ForEach-Object {
        $stats = Get-MailboxStatistics $_.Identity -ErrorAction SilentlyContinue
        @{
            DisplayName        = $_.DisplayName
            PrimarySmtpAddress = $_.PrimarySmtpAddress
            RecipientType      = $_.RecipientTypeDetails
            ArchiveStatus      = $_.ArchiveStatus
            ForwardingAddress  = $_.ForwardingAddress
            ForwardingSmtp     = $_.ForwardingSmtpAddress
            DeliverAndForward  = $_.DeliverToMailboxAndForward
            TotalItemSize      = if ($stats) { "$($stats.TotalItemSize)" } else { "N/A" }
        }
    }
    $result.mailboxes = $mbxData
} catch { $result.mailboxes_error = "$_" }

# ── Transport Rules ───────────────────────────────────────────────────────────
try {
    $rules = Get-TransportRule -ErrorAction SilentlyContinue
    $result.transport_rules = $rules | ForEach-Object {
        @{ Name = $_.Name; State = $_.State; Priority = $_.Priority; Description = $_.Description }
    }
} catch { $result.transport_rules_error = "$_" }

# ── Connectors ────────────────────────────────────────────────────────────────
try {
    $inConn  = Get-InboundConnector  -ErrorAction SilentlyContinue
    $outConn = Get-OutboundConnector -ErrorAction SilentlyContinue
    $result.connectors = @{
        inbound  = $inConn  | ForEach-Object { @{ Name = $_.Name; Enabled = $_.Enabled; Type = $_.ConnectorType; RequireTls = $_.RequireTls } }
        outbound = $outConn | ForEach-Object { @{ Name = $_.Name; Enabled = $_.Enabled; Type = $_.ConnectorType; TlsSettings = "$($_.TlsSettings)" } }
    }
} catch { $result.connectors_error = "$_" }

# ── Anti-Phish ────────────────────────────────────────────────────────────────
try {
    $result.anti_phish = Get-AntiPhishPolicy -ErrorAction SilentlyContinue | ForEach-Object {
        @{
            Name                       = $_.Name
            IsDefault                  = $_.IsDefault
            EnableTargetedUserProtection = $_.EnableTargetedUserProtection
            EnableSpoofIntelligence    = $_.EnableSpoofIntelligence
            EnableFirstContactSafetyTips = $_.EnableFirstContactSafetyTips
        }
    }
} catch { $result.anti_phish_error = "$_" }

# ── Anti-Spam ─────────────────────────────────────────────────────────────────
try {
    $result.anti_spam = Get-HostedContentFilterPolicy -ErrorAction SilentlyContinue | ForEach-Object {
        @{
            Name                      = $_.Name
            SpamAction                = $_.SpamAction
            HighConfidenceSpamAction  = $_.HighConfidenceSpamAction
            BulkSpamAction            = $_.BulkSpamAction
        }
    }
} catch { $result.anti_spam_error = "$_" }

# ── DKIM ──────────────────────────────────────────────────────────────────────
try {
    $result.dkim = Get-DkimSigningConfig -ErrorAction SilentlyContinue | ForEach-Object {
        @{
            Domain  = $_.Domain
            Enabled = $_.Enabled
            Status  = $_.Status
            KeySize = $_.KeySize
        }
    }
} catch { $result.dkim_error = "$_" }

# ── Safe Links / Attachments ──────────────────────────────────────────────────
try {
    $safeLinks = Get-SafeLinksPolicy -ErrorAction SilentlyContinue | ForEach-Object {
        @{ Name = $_.Name; IsEnabled = $_.IsEnabled; ScanUrls = $_.ScanUrls }
    }
    $safeAtt = Get-SafeAttachmentPolicy -ErrorAction SilentlyContinue | ForEach-Object {
        @{ Name = $_.Name; Enable = $_.Enable; Action = $_.Action }
    }
    $result.defender_policies = @{ safe_links = $safeLinks; safe_attachments = $safeAtt }
} catch { $result.defender_policies_error = "$_" }

# ── Quarantine Policies ───────────────────────────────────────────────────────
try {
    $result.quarantine_policies = Get-QuarantinePolicy -ErrorAction SilentlyContinue | ForEach-Object {
        @{ Name = $_.Name; Type = $_.QuarantinePolicyType; EndUserActions = "$($_.EndUserQuarantinePermissions)" }
    }
} catch { $result.quarantine_policies_error = "$_" }

# ── Org Config ────────────────────────────────────────────────────────────────
try {
    $oc = Get-OrganizationConfig -ErrorAction SilentlyContinue
    $result.org_config = @{
        OAuth2ClientProfileEnabled                 = $oc.OAuth2ClientProfileEnabled
        MapiHttpEnabled                            = $oc.MapiHttpEnabled
        DefaultAuthenticationPolicy               = $oc.DefaultAuthenticationPolicy
        SmtpClientAuthenticationDisabled          = $oc.SmtpClientAuthenticationDisabled
        AuditDisabled                              = $oc.AuditDisabled
        ActivityBasedAuthenticationTimeoutEnabled = $oc.ActivityBasedAuthenticationTimeoutEnabled
        ActivityBasedAuthenticationTimeoutInterval = "$($oc.ActivityBasedAuthenticationTimeoutInterval)"
    }
} catch { $result.org_config_error = "$_" }

# ── Admin Audit Log Config (Unified Audit Log ingestion — CIS 9.1) ────────────
# Isolated from Org Config on purpose: this is a separate cmdlet, and its
# failure must not take the org-config read down with it. A null $aalc leaves
# UnifiedAuditLogIngestionEnabled = $null, which serialises to JSON null and is
# read downstream as "not collected" (cannot-verify), never a false pass/fail.
try {
    $aalc = Get-AdminAuditLogConfig -ErrorAction SilentlyContinue
    $result.admin_audit_log_config = @{
        UnifiedAuditLogIngestionEnabled = $aalc.UnifiedAuditLogIngestionEnabled
    }
} catch { $result.admin_audit_log_config_error = "$_" }

# ── Mailbox Forwarding ────────────────────────────────────────────────────────
try {
    $fwd = Get-Mailbox -ResultSize Unlimited -ErrorAction SilentlyContinue |
           Where-Object { $_.ForwardingAddress -or $_.ForwardingSmtpAddress }
    $result.forwarding = $fwd | ForEach-Object {
        @{
            DisplayName        = $_.DisplayName
            PrimarySmtpAddress = $_.PrimarySmtpAddress
            ForwardingAddress  = $_.ForwardingAddress
            ForwardingSmtp     = $_.ForwardingSmtpAddress
            DeliverAndForward  = $_.DeliverToMailboxAndForward
        }
    }
} catch { $result.forwarding_error = "$_" }

# ── Inbox Rules (external forwarding) ────────────────────────────────────────
try {
    $extRules = @()
    $userMbx = Get-Mailbox -RecipientTypeDetails UserMailbox -ResultSize Unlimited -ErrorAction SilentlyContinue
    foreach ($mb in $userMbx) {
        try {
            $rules = Get-InboxRule -Mailbox $mb.Identity -ErrorAction Stop |
                     Where-Object { $_.ForwardTo -or $_.ForwardAsAttachmentTo -or $_.RedirectTo }
            foreach ($rule in $rules) {
                $targets = @($rule.ForwardTo) + @($rule.ForwardAsAttachmentTo) + @($rule.RedirectTo) | Where-Object { $_ }
                $extRules += @{
                    Mailbox = $mb.PrimarySmtpAddress
                    Rule    = $rule.Name
                    Enabled = $rule.Enabled
                    Targets = $targets
                }
            }
        } catch { <# skip inaccessible mailbox #> }
    }
    $result.inbox_rules_external = $extRules
} catch { $result.inbox_rules_error = "$_" }

# ── DLP Policies ─────────────────────────────────────────────────────────────
try {
    # Connect to Security & Compliance
    Connect-IPPSSession -AppId $clientId -Certificate $cert -Organization $orgDomain -ShowBanner:$false -ErrorAction Stop
    $result.dlp_policies = Get-DlpCompliancePolicy -ErrorAction SilentlyContinue | ForEach-Object {
        @{ Name = $_.Name; Mode = $_.Mode; Workloads = "$($_.Workload -join ',')"; Priority = $_.Priority }
    }
    $result.retention_policies = Get-RetentionCompliancePolicy -ErrorAction SilentlyContinue | ForEach-Object {
        @{ Name = $_.Name; Enabled = $_.Enabled; Workloads = "$($_.Workload -join ',')" }
    }
} catch {
    $result.dlp_error = "$_"
    $result.dlp_policies = @()
    $result.retention_policies = @()
}

# ── Mailbox Delegation (SendAs / FullAccess) ──────────────────────────────
try {
    $delegations = @()
    $allMbx = Get-Mailbox -ResultSize Unlimited -ErrorAction SilentlyContinue

    foreach ($mbx in $allMbx) {
        # FullAccess permissions
        $fullAccess = Get-MailboxPermission -Identity $mbx.Identity -ErrorAction SilentlyContinue |
            Where-Object { $_.User -ne "NT AUTHORITY\SELF" -and $_.AccessRights -contains "FullAccess" -and -not $_.Deny }

        foreach ($perm in $fullAccess) {
            $delegations += @{
                Mailbox  = $mbx.UserPrincipalName
                Type     = "FullAccess"
                Delegate = $perm.User.ToString()
            }
        }

        # SendAs permissions
        $sendAs = Get-RecipientPermission -Identity $mbx.Identity -ErrorAction SilentlyContinue |
            Where-Object { $_.Trustee -ne "NT AUTHORITY\SELF" -and $_.AccessRights -contains "SendAs" }

        foreach ($perm in $sendAs) {
            $delegations += @{
                Mailbox  = $mbx.UserPrincipalName
                Type     = "SendAs"
                Delegate = $perm.Trustee.ToString()
            }
        }
    }

    $result.mailbox_delegations = $delegations
    $result.mailbox_delegation_count = $delegations.Count
} catch {
    $result.mailbox_delegations = @()
    $result.mailbox_delegation_count = 0
    $result.mailbox_delegation_error = $_.ToString()
}

# ── Disconnect ────────────────────────────────────────────────────────────────
try { Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue } catch {}

# ── Output ────────────────────────────────────────────────────────────────────
$result | ConvertTo-Json -Depth 8 -Compress
