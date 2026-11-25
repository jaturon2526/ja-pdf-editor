"""Tests for bundled Thailand NRCA / Thai Digital ID CA trust roots and intermediate chain validation."""
from __future__ import annotations

import datetime as dt
import io

import fitz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers

from app.services.pdf_service import properties


def _gen_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_cert(subject_cn: str, issuer_cn: str, key, issuer_key, *, is_ca: bool, days: int = 365):
    now = dt.datetime.now(dt.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
    )
    if is_ca:
        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    else:
        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    return builder.sign(issuer_key, hashes.SHA256())


def _sign_pdf_with_leaf_only(leaf_key, leaf_cert) -> bytes:
    """Create a 1-page PDF signed with only the end-entity cert (no intermediate embedded)."""
    doc = fitz.open()
    doc.new_page()
    raw = doc.tobytes()
    doc.close()

    from asn1crypto import keys as asn1_keys
    from asn1crypto import x509 as asn1_x509

    leaf_der = leaf_cert.public_bytes(serialization.Encoding.DER)
    key_der = leaf_key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    signer = signers.SimpleSigner(
        signing_cert=asn1_x509.Certificate.load(leaf_der),
        signing_key=asn1_keys.PrivateKeyInfo.load(key_der),
        cert_registry=None,
    )
    w = IncrementalPdfFileWriter(io.BytesIO(raw))
    fields.append_signature_field(w, fields.SigFieldSpec(sig_field_name="Sig1"))
    out = io.BytesIO()
    signers.sign_pdf(
        w,
        signers.PdfSignatureMetadata(field_name="Sig1"),
        signer=signer,
        output=out,
    )
    return out.getvalue()


def test_bundled_thailand_nrca_and_tdid_g3_loaded(monkeypatch):
    """Bundled Thailand NRCA G1 root and Thai Digital ID CA G3 intermediate load into trust context."""
    monkeypatch.setattr(properties, "_TRUST_CERTS", None)
    ctx = properties._get_trust_context()
    assert ctx is not None

    root_cns = {
        cert.subject.native.get("common_name")
        for cert in properties._load_trusted_dir(properties._BUNDLED_TRUSTED_CERTS_DIR)[0]
    }
    inter_cns = {
        cert.subject.native.get("common_name")
        for cert in properties._load_trusted_dir(properties._BUNDLED_TRUSTED_CERTS_DIR)[1]
    }
    assert "Thailand National Root Certification Authority - G1" in root_cns
    assert "Thai Digital ID CA G3" in inter_cns


def test_trusted_ca_chain_with_separate_root_and_intermediate(client, make_user, upload, tmp_path, monkeypatch):
    """PDF signed by leaf cert (without embedded intermediate) is trusted when root + intermediate are in trust dir."""
    root_key = _gen_key()
    root_cert = _build_cert("Test Thai Root CA", "Test Thai Root CA", root_key, root_key, is_ca=True)
    inter_key = _gen_key()
    inter_cert = _build_cert("Test TDID Sub CA", "Test Thai Root CA", inter_key, root_key, is_ca=True)
    leaf_key = _gen_key()
    leaf_cert = _build_cert("Somchai Tester", "Test TDID Sub CA", leaf_key, inter_key, is_ca=False)

    signed_pdf = _sign_pdf_with_leaf_only(leaf_key, leaf_cert)

    # Write Root as DER (.cer) and Intermediate as PEM (.pem) to verify both formats + root/intermediate split
    (tmp_path / "root.cer").write_bytes(root_cert.public_bytes(serialization.Encoding.DER))
    (tmp_path / "inter.pem").write_bytes(inter_cert.public_bytes(serialization.Encoding.PEM))

    monkeypatch.setattr(properties, "_CUSTOM_TRUSTED_CERTS_DIR", tmp_path)
    monkeypatch.setattr(properties, "_TRUST_CERTS", None)

    _, h = make_user()
    sid = upload(h, signed_pdf, name="tdid-signed.pdf")
    r = client.get(f"/pdf/{sid}/properties", headers=h)
    assert r.status_code == 200, r.text
    sigs = r.json()["signatures"]
    assert len(sigs) == 1
    assert sigs[0]["is_valid"] is True
    assert sigs[0]["is_trusted"] is True
    assert sigs[0]["cert_subject_cn"] == "Somchai Tester"
    assert sigs[0]["cert_issuer_cn"] == "Test TDID Sub CA"
