"""Request models for the customer registry, notes and tags endpoints.

The defaults are the ones the handlers used to pass to ``body.get``. Where a
handler answered a missing value with its own translated message — no customer
id, no name — the field stays optional here so that message is still what the
operator reads, rather than a field error.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field


class CustomerRef(BaseModel):
    """A customer id on its own: the one to archive."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str = ""


class ManualCustomerCreate(BaseModel):
    """A customer added by hand, without M365 setup.

    Null and absent both mean empty, as ``(body.get(k) or "")`` did.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    primary_domain: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    org_number: str | None = None
    notes: str | None = None


class CustomerNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str = ""


class CustomerTags(BaseModel):
    """The whole tag list for the customer named in the path."""

    model_config = ConfigDict(extra="forbid")

    tags: list[str] = []


# A provider record id as the link picker sends it: the candidate's id, which
# is a number or a string depending on the provider, or null to unlink.
_ProviderId = Union[int, str, None]


class CustomerLinks(BaseModel):
    """Bind a customer to its Autotask, IT Glue and myITprocess records.

    Only the keys present are changed (``model_fields_set``); null or an empty
    string clears that binding. The Autotask id is checked as a number by the
    handler, which has the message for one that is not.
    """

    model_config = ConfigDict(extra="forbid")

    autotask_account_id: _ProviderId = None
    itglue_org_id: _ProviderId = None
    myitprocess_account_id: _ProviderId = None


class CredentialResetTarget(BaseModel):
    """Whose M365 credentials to wipe or renew. Required: there is no default."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=1)
