# Provenance and security

`ProvenanceVerifier` is a protocol. HNG ships a compatibility caller-assertion verifier, a static externally authenticated identity adapter, and a callable adapter for established signature or identity services. It intentionally does not define a cryptographic protocol.

On ingestion HNG persists verifier name, verification status, resolved identity, signature/reference, and verification timestamp. Trust policy distinguishes verified and unverified records and still applies source- and kind-specific ceilings. A signed payload is not automatically true; it establishes origin.

Production deployments should connect the callable adapter to their existing PKI, workload identity, signed-document, or tool-result verification service. Private and tenant access checks remain exact SQL policy and occur before vector ranking. Corrupt JSON metadata fails closed, and unauthorized perfect-nearest-neighbor records are not candidates.

Limitations: the bundled static verifier is an integration example, not certificate-chain validation; key rotation, revocation, replay protection, and trust-store operations remain the external verifier's responsibility.

