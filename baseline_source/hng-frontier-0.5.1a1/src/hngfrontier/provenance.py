from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Protocol, runtime_checkable

from .governance import EvidenceProvenance, utc_now_iso


@dataclass(frozen=True, slots=True)
class VerificationResult:
    status: str
    verifier: str
    identity: str = ""
    signature_reference: str = ""
    verified_at: str = ""
    details: Mapping[str, object] | None = None

    @property
    def verified(self) -> bool:
        return self.status == "verified"


@runtime_checkable
class ProvenanceVerifier(Protocol):
    name: str
    def verify(self, provenance: EvidenceProvenance, *, content: str, metadata: Mapping[str, object]) -> VerificationResult: ...


class CallerAssertionVerifier:
    """Compatibility verifier. It records that trust came from the caller, not cryptographic verification."""
    name = "caller-assertion"

    def verify(self, provenance: EvidenceProvenance, *, content: str,
               metadata: Mapping[str, object]) -> VerificationResult:
        status = "verified" if provenance.verified else "unverified"
        return VerificationResult(status, self.name, provenance.actor_id or provenance.source_id,
                                  provenance.signature, utc_now_iso(), {"mechanism": "caller_asserted"})


class StaticIdentityVerifier:
    """Adapter for identities already authenticated by an external service or trust store."""
    name = "static-identity"

    def __init__(self, identities: Mapping[str, str]):
        self.identities = dict(identities)

    def verify(self, provenance: EvidenceProvenance, *, content: str,
               metadata: Mapping[str, object]) -> VerificationResult:
        identity = self.identities.get(provenance.source_id, "")
        return VerificationResult("verified" if identity else "rejected", self.name, identity,
                                  provenance.signature, utc_now_iso(), {"source_id": provenance.source_id})


def verified_provenance(provenance: EvidenceProvenance, result: VerificationResult) -> EvidenceProvenance:
    return replace(provenance, verified=result.verified, verifier=result.verifier,
                   verification_status=result.status, identity=result.identity,
                   signature_reference=result.signature_reference,
                   verified_at=result.verified_at or utc_now_iso())


class CallableProvenanceVerifier:
    """Delegates signature/authentication checks to an established external verifier."""

    def __init__(self, name: str, callback: Callable[[EvidenceProvenance, str, Mapping[str, object]], VerificationResult]):
        self.name = str(name); self.callback = callback

    def verify(self, provenance: EvidenceProvenance, *, content: str,
               metadata: Mapping[str, object]) -> VerificationResult:
        result = self.callback(provenance, content, metadata)
        if not isinstance(result, VerificationResult):
            raise TypeError("provenance callback must return VerificationResult")
        return result
