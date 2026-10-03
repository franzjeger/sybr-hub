from pydantic import BaseModel, Field


class EntraSettings(BaseModel):
    block_user_consent: bool = Field(
        default=True, description="Block users from consenting to apps on company behalf"
    )
    block_app_registration: bool = Field(
        default=True, description="Block users from registering custom applications"
    )
    block_tenant_creation: bool = Field(
        default=True, description="Block users from creating new Entra tenants"
    )
    restrict_guest_access: bool = Field(
        default=True, description="Guests have limited access to directory objects"
    )
    mdm_auto_enrollment: bool = Field(default=True, description="Set MDM User Scope to 'All'")


class ConditionalAccessSettings(BaseModel):
    block_legacy_auth: bool = Field(
        default=True, description="Block legacy authentication (POP3/IMAP)"
    )
    require_mfa_all: bool = Field(
        default=True, description="Require MFA for all users (except break-glass)"
    )
    require_mfa_admins: bool = Field(default=True, description="Require MFA for all admin roles")
    require_compliant_device: bool = Field(
        default=False, description="Require compliant device or hybrid joined for access"
    )
    block_high_risk_countries: bool = Field(
        default=False, description="Block sign-ins from high-risk countries"
    )
    sign_in_risk_mfa: bool = Field(
        default=False, description="Require MFA for medium/high sign-in risk (requires P2)"
    )
    user_risk_password_change: bool = Field(
        default=False, description="Require password change for high user risk (requires P2)"
    )


class IntuneConfigSettings(BaseModel):
    silent_bitlocker: bool = Field(
        default=True, description="Silently encrypt OS drive with BitLocker and backup to Entra"
    )
    windows_laps: bool = Field(
        default=True, description="Configure Windows LAPS and backup to Entra"
    )
    defender_av_cloud: bool = Field(
        default=True, description="Enable Defender AV Real-time and Cloud-delivered protection"
    )
    asr_rules_standard: bool = Field(
        default=True,
        description="Deploy standard Attack Surface Reduction (ASR) rules in block mode",
    )
    onedrive_kfm: bool = Field(
        default=True, description="Silently redirect Windows known folders to OneDrive"
    )
    windows_hello_for_business: bool = Field(
        default=False, description="Enable Windows Hello for Business"
    )


class IntuneComplianceSettings(BaseModel):
    require_bitlocker: bool = Field(
        default=True, description="Require BitLocker encryption to be compliant"
    )
    require_antivirus: bool = Field(default=True, description="Require Antivirus to be active")
    require_firewall: bool = Field(default=True, description="Require Firewall to be active")
    max_inactivity_lock_minutes: int = Field(
        default=15, description="Maximum minutes of inactivity before password is required"
    )
    minimum_os_version_windows: str = Field(
        default="10.0.19045", description="Minimum OS version for Windows 10/11"
    )


class M365SecurityBaseline(BaseModel):
    """The desired state configuration for a tenant's security posture."""

    entra: EntraSettings = Field(default_factory=EntraSettings)
    conditional_access: ConditionalAccessSettings = Field(default_factory=ConditionalAccessSettings)
    intune_config: IntuneConfigSettings = Field(default_factory=IntuneConfigSettings)
    intune_compliance: IntuneComplianceSettings = Field(default_factory=IntuneComplianceSettings)
