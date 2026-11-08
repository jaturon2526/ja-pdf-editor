"""ใบรับรองระบบจาก CA (SIGNING_SEAL_P12) แทน self-signed"""
import datetime as dt
import io

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.core.config import settings
from app.services import signing_pdf
from tests.test_signing import _email, _sign_electronic
from tests.test_signing_phase3 import _box, _create


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Acme Co")])


def _make_ca_p12(password: bytes, days: int = 365) -> bytes:
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = (x509.CertificateBuilder().subject_name(_name("Acme Test Root CA")).issuer_name(_name("Acme Test Root CA"))
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder().subject_name(_name("Acme Document Seal")).issuer_name(ca.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=days))
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"seal", key, cert, [ca],
                                                 serialization.BestAvailableEncryption(password))


@pytest.fixture
def seal_p12(tmp_path, monkeypatch):
    path = tmp_path / "org-seal.p12"
    path.write_bytes(_make_ca_p12(b"seal-pass"))
    monkeypatch.setattr(settings, "SIGNING_SEAL_P12", str(path))
    monkeypatch.setattr(settings, "SIGNING_SEAL_P12_PASSWORD", "seal-pass")
    signing_pdf._configured_seal_cache.clear()
    yield path
    signing_pdf._configured_seal_cache.clear()


def test_electronic_signature_uses_configured_ca_seal_with_chain(client, make_user, upload, seal_p12):
    _, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **_box(0)}]).json()["id"]
    assert _sign_electronic(client, signer, rid).status_code == 200

    report = client.get(f"/signing/requests/{rid}/verify", headers=owner).json()["signatures"]
    assert report[0]["valid"] and report[0]["signer"] == "Acme Document Seal"

    from pyhanko.pdf_utils.reader import PdfFileReader

    data = client.get(f"/signing/requests/{rid}/document", headers=owner).content
    sig = PdfFileReader(io.BytesIO(data)).embedded_signatures[0]
    embedded = {c.subject.native["common_name"] for c in sig.other_embedded_certs}
    assert "Acme Test Root CA" in embedded  # chain ฝังไปกับลายเซ็น ให้โปรแกรมอ่าน PDF ต่อ chain ได้

    evidence = client.get(f"/signing/requests/{rid}/evidence", headers=owner).content
    assert signing_pdf.signature_report(evidence)[0]["signer"] == "Acme Document Seal"


def test_seal_info_reports_ca_chain_and_expiry(seal_p12):
    info = signing_pdf.seal_info()
    assert info["source"] == "p12" and not info["self_signed"]
    assert info["subject"] == "Acme Document Seal" and info["issuer"] == "Acme Test Root CA"
    assert info["chain"] == ["Acme Test Root CA"] and info["warnings"] == []


def test_seal_info_warns_when_expiring_soon(tmp_path, monkeypatch):
    path = tmp_path / "soon.p12"
    path.write_bytes(_make_ca_p12(b"pw", days=10))
    monkeypatch.setattr(settings, "SIGNING_SEAL_P12", str(path))
    monkeypatch.setattr(settings, "SIGNING_SEAL_P12_PASSWORD", "pw")
    signing_pdf._configured_seal_cache.clear()
    try:
        assert any("หมดอายุในอีก" in w for w in signing_pdf.seal_info()["warnings"])
    finally:
        signing_pdf._configured_seal_cache.clear()


def test_wrong_seal_password_fails_instead_of_falling_back(client, make_user, upload, seal_p12, monkeypatch):
    monkeypatch.setattr(settings, "SIGNING_SEAL_P12_PASSWORD", "wrong")
    _, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **_box(0)}]).json()["id"]
    r = _sign_electronic(client, signer, rid)
    assert r.status_code == 400 and "SIGNING_SEAL_P12" in r.json()["detail"]
    # ยังไม่ถูกบันทึกว่าลงนามแล้ว — ลองใหม่ได้หลังแก้ค่า
    assert client.get(f"/signing/requests/{rid}", headers=signer).json()["my_turn"]


def test_self_signed_seal_is_reported_as_such(monkeypatch):
    monkeypatch.setattr(settings, "SIGNING_SEAL_P12", None)
    info = signing_pdf.seal_info()
    assert info["source"] == "self-signed" and info["self_signed"] and info["warnings"]


# ---------------------------------------------------------------------------
# เติม chain จาก AIA เมื่อ .p12 มีแค่ใบรับรองของเจ้าของ
# ---------------------------------------------------------------------------

def _p12_without_chain(aia_url: str):
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = (x509.CertificateBuilder().subject_name(_name("Thai Test CA G3")).issuer_name(_name("Thai Test CA G3"))
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    aia = x509.AuthorityInformationAccess([x509.AccessDescription(
        x509.oid.AuthorityInformationAccessOID.CA_ISSUERS, x509.UniformResourceIdentifier(aia_url))])
    cert = (x509.CertificateBuilder().subject_name(_name("Some Person")).issuer_name(ca.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
            .add_extension(aia, critical=False)
            .sign(ca_key, hashes.SHA256()))
    p12 = pkcs12.serialize_key_and_certificates(b"me", key, cert, None, serialization.BestAvailableEncryption(b"pw"))
    return p12, ca.public_bytes(serialization.Encoding.DER)


def test_missing_chain_is_downloaded_from_aia_once(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    url = "http://ca.example.test/issuer.cer"
    p12, ca_der = _p12_without_chain(url)
    calls = []
    monkeypatch.setattr(signing_pdf, "_fetch_url", lambda u: calls.append(u) or ca_der)

    signer = signing_pdf.load_pkcs12_signer(p12, "pw")
    assert "Thai Test CA G3" in {c.subject.native["common_name"] for c in signer.cert_registry}
    signing_pdf.load_pkcs12_signer(p12, "pw")
    assert calls == [url]  # ครั้งที่สองใช้ cache


def test_unreachable_aia_does_not_block_signing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    p12, _ = _p12_without_chain("http://ca.example.test/missing.cer")

    def boom(_url):
        raise OSError("network down")

    monkeypatch.setattr(signing_pdf, "_fetch_url", boom)
    signer = signing_pdf.load_pkcs12_signer(p12, "pw")
    assert signer.signing_cert.subject.native["common_name"] == "Some Person"


def test_pem_and_pkcs7_issuer_files_are_understood():
    _, ca_der = _p12_without_chain("http://x.test/a.cer")
    pem = b"-----BEGIN CERTIFICATE-----\n" + __import__("base64").encodebytes(ca_der) + b"-----END CERTIFICATE-----\n"
    assert signing_pdf._parse_certs(pem)[0].subject.native["common_name"] == "Thai Test CA G3"
    assert signing_pdf._parse_certs(ca_der)[0].subject.native["common_name"] == "Thai Test CA G3"
